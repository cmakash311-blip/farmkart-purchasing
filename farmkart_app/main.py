"""Farmkart Foods online peanut purchasing MVP. Independent implementation.

Run database init and create named users with farmkart_app.bootstrap before startup.
Do NOT expose this pilot to the public internet without infrastructure/security review.
"""
import csv, io, os, uuid
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from .db import get_db
from .models import Branch, User, SessionToken, Farmer, BillSequence, Purchase, PurchaseLine, Payment, Audit, Material
from .security import COOKIE_NAME, hash_token, check_password, encode_password, new_session, get_session, require_user, check_branch, allow, can_access

# Fail closed if someone mistakenly starts the pilot in production mode with demo settings.
if os.getenv('APP_ENV') == 'production':
    raw_url = os.getenv('DATABASE_URL', '')
    is_pg = (
        raw_url.startswith('postgresql+psycopg://') or 
        raw_url.startswith('postgresql://') or 
        raw_url.startswith('postgres://')
    )
    if not is_pg:
        raise RuntimeError('Production requires a central PostgreSQL DATABASE_URL')
    if os.getenv('COOKIE_SECURE') != '1':
        raise RuntimeError('Production requires COOKIE_SECURE=1 and HTTPS')
app = FastAPI(title='Farmkart Foods Online Purchasing', docs_url=None if os.getenv('APP_ENV')=='production' else '/docs')

@app.middleware('http')
async def security_headers(request:Request, call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    if request.url.path.startswith('/api/') or request.url.path=='/':
        response.headers['Cache-Control']='no-store'
    return response

STATIC = Path(__file__).parent/'static'
INR = Decimal('0.01')
KG = Decimal('0.001')
MAX = Decimal('999999999999.99')

def d(value, places=INR):
    try:
        out = Decimal(str(value))
        if not out.is_finite(): raise ValueError()
        return out.quantize(places, rounding=ROUND_HALF_UP)
    except (ValueError, InvalidOperation, TypeError): raise HTTPException(422,'Invalid decimal amount or weight')

def inr(v): return format(d(v),'.2f')
def kg(v): return format(d(v,KG),'.3f')
def today(): return datetime.now(ZoneInfo('Asia/Kolkata')).date()
def fy(dt:date):
    y=dt.year if dt.month>=4 else dt.year-1
    return f'{y}-{str(y+1)[-2:]}'

def audit(db, user, branch_id, action, entity, id_, details=''):
    db.add(Audit(user_id=user.id, branch_id=branch_id, action=action, entity=entity, entity_id=id_, details=details))

def pay_summary(bill: Purchase):
    if getattr(bill, 'status', '') == 'VOID':
        return {'cleared': inr(Decimal('0')), 'pending': inr(Decimal('0')), 'outstanding': inr(Decimal('0')), 'unallocated': inr(Decimal('0'))}
    cleared=sum((d(p.amount) for p in bill.payments if p.status=='CLEARED'),Decimal('0'))
    pending=sum((d(p.amount) for p in bill.payments if p.status=='PENDING'),Decimal('0'))
    return {'cleared':inr(cleared),'pending':inr(pending),'outstanding':inr(max(Decimal('0'),d(bill.payable)-cleared)), 'unallocated':inr(max(Decimal('0'),d(bill.payable)-cleared-pending))}

def purchase_view(p:Purchase,detail=False):
    # Point 1: Get cheque details from Payment records for receipt display
    cheque_pays=[x for x in p.payments if x.method=='CHEQUE']
    total_cheque_sum=sum((d(x.amount) for x in cheque_pays), Decimal('0'))
    cheque_pay=cheque_pays[0] if cheque_pays else None
    data={'id':p.id,'number':p.number,'date':str(p.purchase_date),'branch_id':p.branch_id,'branch':p.branch.name,'farmer_id':p.farmer_id,'farmer':p.farmer.name,'village':p.farmer.village,'mobile':p.farmer.mobile,'rst':p.rst_number,'vehicle':p.vehicle_number,'total_bags':getattr(p,'total_bags',0) or 0,'gross_kg':kg(p.gross_kg),'kapat_kg':kg(p.kapat_kg),'net_kg':kg(p.net_kg),'gross_value':inr(p.gross_value),'weighbridge_charges':inr(p.weighbridge_charges),'other_deductions':inr(p.other_deductions),'market_transport_cost':inr(getattr(p,'market_transport_cost',Decimal('0')) or Decimal('0')),'unload_at_godown':bool(getattr(p,'unload_at_godown',False)),'round_adjustment':inr(p.round_adjustment),'payable':inr(p.payable),'status':p.status,'notes':p.notes,'payments_summary':pay_summary(p),'cash_paid':inr(getattr(p,'cash_paid',Decimal('0')) or Decimal('0')),'pay_later_cash':inr(getattr(p,'pay_later_cash',Decimal('0')) or Decimal('0')),'pay_later_date':str(getattr(p,'pay_later_date',None) or ''),'cheque_number':cheque_pay.reference if cheque_pay else '','cheque_date':str(cheque_pay.instrument_date or '') if cheque_pay else '','cheque_amount':inr(total_cheque_sum),'cheques':[{'number':x.reference,'date':str(x.instrument_date or ''),'amount':inr(x.amount)} for x in cheque_pays]}
    if detail:
        data['lines']=[{'variety':x.variety,'material_id':getattr(x,'material_id',None),'material_name':(x.material_ref.name if getattr(x,'material_ref',None) else x.variety),'bag_count':getattr(x,'bag_count',0) or 0,'bag_tare_kg':kg(getattr(x,'bag_tare_kg',0) or 0),'gross_kg':kg(x.gross_kg),'kapat_kg':kg(x.kapat_kg),'net_kg':kg(x.net_kg),'rate_per_20kg':inr(x.rate_per_20kg),'amount':inr(x.line_amount)} for x in p.lines]
        data['payments']=[payment_view(x,p.number,p.farmer.name,p.branch_id,str(p.purchase_date),p.farmer.village) for x in p.payments]
    return data

def payment_view(p:Payment, bill_number=None, farmer=None, branch_id=None, bill_date=None, village=None):
    b_date = bill_date or (str(p.purchase.purchase_date) if getattr(p, 'purchase', None) and getattr(p.purchase, 'purchase_date', None) else '')
    vlg = village or (p.purchase.farmer.village if getattr(p, 'purchase', None) and getattr(p.purchase, 'farmer', None) and getattr(p.purchase.farmer, 'village', None) else '')
    return {
        'id': p.id,
        'purchase_id': p.purchase_id,
        'bill_number': bill_number or (p.purchase.number if getattr(p, 'purchase', None) else ''),
        'bill_date': b_date,
        'farmer': farmer or (p.purchase.farmer.name if getattr(p, 'purchase', None) and getattr(p.purchase, 'farmer', None) else ''),
        'village': vlg,
        'branch_id': branch_id or (p.purchase.branch_id if getattr(p, 'purchase', None) else None),
        'method': p.method,
        'status': p.status,
        'amount': inr(p.amount),
        'reference': p.reference,
        'instrument_date': str(p.instrument_date or ''),
        'created_at': str(p.created_at)
    }

def scoped(query,user,model):
    return query if user.role=='OWNER' else query.where(model.branch_id==user.branch_id)

class LoginIn(BaseModel):
    username:str
    password:str

class FarmerIn(BaseModel):
    name:str=Field(min_length=2,max_length=140)
    village:str=Field(min_length=2,max_length=140)
    mobile:str=Field(default='',max_length=20)
    cooperative:str=Field(default='',max_length=140)

class ChequeIn(BaseModel):
    cheque_number: str = Field(min_length=1, max_length=30)
    cheque_date: date | None = None
    cheque_amount: Decimal = Field(gt=0, le=1000000000)


class MaterialIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str | None = Field(default=None, max_length=40)
    hsn_code: str = Field(default='1202', max_length=20)
    default_rate: Decimal = Field(default=Decimal('0'), ge=0)

class MaterialUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    default_rate: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None

class LineIn(BaseModel):
    variety:str=Field(min_length=2,max_length=80)
    bag_count:int=Field(default=0,ge=0,le=100000)
    bag_tare_kg:Decimal=Field(default=Decimal('0'),ge=0,le=100)
    gross_kg:Decimal=Field(gt=0,le=10000000)
    kapat_kg:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    rate_per_20kg:Decimal=Field(gt=0,le=10000000)

class PurchaseIn(BaseModel):
    idem_key: str=Field(min_length=16,max_length=100)
    branch_id:int
    farmer_id:int|None=None
    # Point 2: Direct farmer entry (auto-lookup or create-on-the-fly)
    farmer_name:str|None=Field(default=None,max_length=140)
    farmer_village:str|None=Field(default=None,max_length=140)
    farmer_mobile:str|None=Field(default=None,max_length=20)
    rst_number:str=Field(default='',max_length=80)
    vehicle_number:str=Field(default='',max_length=60)
    # Point 4: Bill Date Picker
    purchase_date:date|None=None
    weighbridge_charges:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    other_deductions:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    # Point 3: Transport & Godown unloading costs
    market_transport_cost:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    unload_at_godown:bool=Field(default=False)
    round_adjustment:Decimal=Field(default=Decimal('0'),ge=-10000000,le=10000000)
    notes:str=Field(default='',max_length=1000)
    lines:list[LineIn]=Field(min_length=1,max_length=25)
    # Point 1: Payment settlement at time of bill creation
    cash_paid:Decimal=Field(default=Decimal('0'),ge=0,le=1000000000)
    pay_later_cash:Decimal=Field(default=Decimal('0'),ge=0,le=1000000000)
    pay_later_date:date|None=None
    cheque_number:str=Field(default='',max_length=30)
    cheque_date:date|None=None
    cheque_amount:Decimal=Field(default=Decimal('0'),ge=0,le=1000000000)
    cheques:list[ChequeIn]=Field(default_factory=list)

class PurchaseUpdateIn(BaseModel):
    branch_id: int | None = None
    farmer_id: int | None = None
    farmer_name: str | None = Field(default=None, max_length=140)
    farmer_village: str | None = Field(default=None, max_length=140)
    farmer_mobile: str | None = Field(default=None, max_length=20)
    rst_number: str = Field(default='', max_length=80)
    vehicle_number: str = Field(default='', max_length=60)
    purchase_date: date | None = None
    weighbridge_charges: Decimal = Field(default=Decimal('0'), ge=0, le=10000000)
    other_deductions: Decimal = Field(default=Decimal('0'), ge=0, le=10000000)
    market_transport_cost: Decimal = Field(default=Decimal('0'), ge=0, le=10000000)
    unload_at_godown: bool = Field(default=False)
    round_adjustment: Decimal = Field(default=Decimal('0'), ge=-10000000, le=10000000)
    notes: str = Field(default='', max_length=1000)
    lines: list[LineIn] = Field(min_length=1, max_length=25)
    cash_paid: Decimal = Field(default=Decimal('0'), ge=0, le=1000000000)
    pay_later_cash: Decimal = Field(default=Decimal('0'), ge=0, le=1000000000)
    pay_later_date: date | None = None
    cheque_number: str = Field(default='', max_length=30)
    cheque_date: date | None = None
    cheque_amount: Decimal = Field(default=Decimal('0'), ge=0, le=1000000000)
    cheques: list[ChequeIn] = Field(default_factory=list)

class PaymentIn(BaseModel):
    idem_key:str=Field(min_length=16,max_length=100)
    method:Literal['CASH','CHEQUE','BANK']
    amount:Decimal=Field(gt=0,le=1000000000)
    reference:str=Field(default='',max_length=100)
    instrument_date:date|None=None

class FarmerPaymentIn(BaseModel):
    idem_key: str = Field(min_length=16, max_length=100)
    method: Literal['CASH', 'CHEQUE', 'BANK']
    amount: Decimal = Field(gt=0, le=1000000000)
    reference: str = Field(default='', max_length=100)
    instrument_date: date | None = None

class PaymentStatusIn(BaseModel):
    status:Literal['CLEARED','BOUNCED']

class BatchPaymentItem(BaseModel):
    payment_id: int
    status: Literal['PENDING', 'CLEARED', 'BOUNCED']
    clearance_date: date | None = None

class BatchPaymentStatusIn(BaseModel):
    items: list[BatchPaymentItem] = Field(min_length=1, max_length=200)

class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    name: str = Field(min_length=2, max_length=120)
    role: Literal['OWNER', 'PURCHASE', 'ACCOUNTS', 'VIEWER']
    branch_id: int | None = None
    password: str = Field(min_length=12, max_length=128)

class UserStatusIn(BaseModel):
    active: bool

class UserResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)

class PurchaseVoidIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

@app.get('/')
def index():
    return FileResponse(STATIC/'index.html', headers={'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0'})

@app.get('/static/{filename}')
def static(filename:str):
    if filename not in ['app.css','app.js']: raise HTTPException(404)
    return FileResponse(STATIC/filename, headers={'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0'})

@app.get('/api/health')
def health(): return {'status':'ok'}

@app.post('/api/login')
def login(request:Request, data:LoginIn, response:Response, db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.username==data.username.strip().lower()))
    if not user or not user.active or not check_password(data.password,user.password_hash):
        raise HTTPException(401,'Incorrect username or password')
    token, record = new_session(db,user)
    is_https = (
        request.headers.get('x-forwarded-proto') == 'https' or
        request.url.scheme == 'https' or
        os.getenv('COOKIE_SECURE', '0') == '1'
    )
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=is_https, samesite='lax', max_age=12*3600, path='/')
    return {
        'ok': True,
        'token': token,
        'csrf_token': record.csrf_token,
        'user': {
            'id': user.id,
            'name': user.full_name,
            'username': user.username,
            'role': user.role,
            'branch_id': user.branch_id,
            'csrf_token': record.csrf_token
        }
    }

@app.post('/api/logout')
def logout(request:Request, response:Response, db:Session=Depends(get_db)):
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else request.cookies.get(COOKIE_NAME, '')
    if token:
        row=db.scalar(select(SessionToken).where(SessionToken.token_hash==hash_token(token)))
        if row: db.delete(row); db.commit()
    response.delete_cookie(COOKIE_NAME,path='/')
    return {'ok':True}

@app.get('/api/me')
def me(user_and_session: tuple[User, SessionToken] = Depends(get_session)):
    user, session = user_and_session
    return {'id':user.id,'name':user.full_name,'username':user.username,'role':user.role,'branch_id':user.branch_id,'csrf_token':session.csrf_token}


def seed_default_materials(db: Session):
    defaults = [
        ('MAT-24', 'મગફળી - 24', Decimal('1000.00')),
        ('MAT-JAVA', 'Java', Decimal('1100.00')),
        ('MAT-BOLD', 'Bold', Decimal('1050.00')),
        ('MAT-G20', 'G-20', Decimal('1150.00')),
        ('MAT-TJ', 'TJ', Decimal('1020.00')),
        ('MAT-PH04', 'PHUT 04', Decimal('980.00')),
        ('MAT-PH12', 'PHUT 12', Decimal('990.00')),
        ('MAT-INSHELL', 'In-shell', Decimal('950.00')),
        ('MAT-OTHER', 'Other', Decimal('1000.00')),
    ]
    for c, n, r in defaults:
        if not db.scalar(select(Material).where((Material.code == c) | (Material.name == n))):
            db.add(Material(code=c, name=n, default_rate=r, active=True))
    db.flush()

@app.get('/api/materials')
def get_materials(all: bool = False, db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Material.id))) or 0
    if count == 0:
        seed_default_materials(db)
        db.commit()
    q = select(Material).order_by(Material.id)
    if not all:
        q = q.where(Material.active == True)
    return [{
        'id': m.id,
        'code': m.code,
        'name': m.name,
        'hsn_code': m.hsn_code,
        'default_rate': inr(m.default_rate),
        'active': m.active
    } for m in db.scalars(q)]

@app.post('/api/materials', status_code=201)
def create_material(data: MaterialIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    allow(user, 'OWNER', 'PURCHASE')
    clean_name = data.name.strip()
    clean_code = (data.code or f"MAT-{uuid.uuid4().hex[:6].upper()}").strip()
    if db.scalar(select(Material).where(func.lower(Material.name) == clean_name.lower())):
        raise HTTPException(400, f"Material '{clean_name}' already exists in master")
    mat = Material(
        code=clean_code,
        name=clean_name,
        hsn_code=data.hsn_code.strip() or '1202',
        default_rate=d(data.default_rate),
        active=True
    )
    db.add(mat)
    db.flush()
    audit(db, user, user.branch_id, 'CREATE_MATERIAL', 'material', mat.id, f"{clean_code} - {clean_name}")
    db.commit()
    return {'id': mat.id, 'code': mat.code, 'name': mat.name, 'default_rate': inr(mat.default_rate), 'active': mat.active}

@app.get('/api/branches')
def branches(user:User=Depends(require_user),db:Session=Depends(get_db)):
    q=select(Branch).order_by(Branch.id)
    if user.role!='OWNER':q=q.where(Branch.id==user.branch_id)
    return [{'id':b.id,'code':b.code,'name':b.name} for b in db.scalars(q)]

@app.get('/api/farmers')
def farmers(search:str='',limit:int=Query(100,ge=1,le=500),user:User=Depends(require_user),db:Session=Depends(get_db)):
    q=select(Farmer).order_by(Farmer.name,Farmer.id).limit(limit)
    if search.strip():
        s=f'%{search.strip()}%'
        q=q.where((Farmer.name.ilike(s))|(Farmer.village.ilike(s))|(Farmer.mobile.ilike(s)))
    return [{'id':f.id,'code':f'FKF-{f.id:07d}','name':f.name,'village':f.village,'mobile':f.mobile,'cooperative':f.cooperative} for f in db.scalars(q)]

@app.post('/api/farmers',status_code=201)
def add_farmer(data:FarmerIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','PURCHASE')
    f=Farmer(name=data.name.strip(),village=data.village.strip(),mobile=data.mobile.strip(),cooperative=data.cooperative.strip())
    db.add(f);db.flush();audit(db,user,user.branch_id,'CREATE_FARMER','farmer',f.id)
    db.commit()
    return {'id':f.id,'code':f'FKF-{f.id:07d}','name':f.name,'village':f.village}

@app.get('/api/farmers/{farmer_id}/ledger')
def farmer_ledger(farmer_id:int,date_from:date|None=None,date_to:date|None=None,user:User=Depends(require_user),db:Session=Depends(get_db)):
    farmer=db.get(Farmer,farmer_id)
    if not farmer:
        raise HTTPException(404,'Farmer not found')
    q=select(Purchase).options(selectinload(Purchase.branch),selectinload(Purchase.payments)).where(Purchase.farmer_id==farmer_id,Purchase.status!='VOID')
    if user.role!='OWNER':
        q=q.where(Purchase.branch_id==user.branch_id)
    bills=list(db.scalars(q.order_by(Purchase.purchase_date.asc(),Purchase.id.asc())))
    raw_entries=[]
    for b in bills:
        total_bags=getattr(b,'total_bags',0) or 0
        raw_entries.append({
            'date':b.purchase_date,'type':'BILL','id':b.id,'ref':b.number,'branch':b.branch.name,
            'description':f"Purchase {total_bags} bags ({kg(b.net_kg)} kg net)",
            'credit':d(b.payable),'debit':Decimal('0.00'),'status':b.status
        })
        for p in b.payments:
            if p.status!='BOUNCED':
                pay_date=p.instrument_date or p.created_at.date()
                raw_entries.append({
                    'date':pay_date,'type':'PAYMENT','id':p.id,'ref':p.reference or f"Payment for {b.number}",'branch':b.branch.name,
                    'description':f"Payment via {p.method} ({p.status})",
                    'credit':Decimal('0.00'),'debit':d(p.amount),'status':p.status
                })
    raw_entries.sort(key=lambda x:(x['date'],0 if x['type']=='BILL' else 1,x['id']))
    opening_balance=Decimal('0.00')
    if date_from:
        for e in raw_entries:
            if e['date']<date_from:
                if e['type']=='BILL':opening_balance+=e['credit']
                elif e['status']=='CLEARED':opening_balance-=e['debit']
    filtered=[e for e in raw_entries if (not date_from or e['date']>=date_from) and (not date_to or e['date']<=date_to)]
    running=opening_balance
    formatted_entries=[]
    for e in filtered:
        if e['type']=='BILL':running+=e['credit']
        elif e['status']=='CLEARED':running-=e['debit']
        formatted_entries.append({
            'date':str(e['date']),'type':e['type'],'ref':e['ref'],'branch':e['branch'],
            'description':e['description'],'credit':inr(e['credit']),'debit':inr(e['debit']),
            'status':e['status'],'running_balance':inr(running)
        })
    total_billed=sum((d(b.payable) for b in bills),Decimal('0'))
    total_cleared=sum((d(p.amount) for b in bills for p in b.payments if p.status=='CLEARED'),Decimal('0'))
    total_pending=sum((d(p.amount) for b in bills for p in b.payments if p.status=='PENDING'),Decimal('0'))
    return {
        'farmer':{'id':farmer.id,'code':f'FKF-{farmer.id:07d}','name':farmer.name,'village':farmer.village,'mobile':farmer.mobile,'cooperative':farmer.cooperative},
        'summary':{
            'total_bills':len(bills),
            'total_bags':sum(getattr(b,'total_bags',0) or 0 for b in bills),
            'total_gross_kg':kg(sum(b.gross_kg for b in bills) if bills else Decimal('0')),
            'total_net_kg':kg(sum(b.net_kg for b in bills) if bills else Decimal('0')),
            'total_billed':inr(total_billed),
            'total_cleared_payments':inr(total_cleared),
            'total_pending_payments':inr(total_pending),
            'outstanding_balance':inr(max(Decimal('0'),total_billed-total_cleared)),
            'unallocated_balance':inr(max(Decimal('0'),total_billed-total_cleared-total_pending)),
        },
        'date_from':str(date_from or ''),'date_to':str(date_to or ''),
        'opening_balance':inr(opening_balance),'closing_balance':inr(running),'entries':formatted_entries
    }

@app.post('/api/farmers/{farmer_id}/payments',status_code=201)
def add_farmer_payment(farmer_id:int,data:FarmerPaymentIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','ACCOUNTS')
    farmer=db.get(Farmer,farmer_id)
    if not farmer:raise HTTPException(404,'Farmer not found')
    q=select(Purchase).options(selectinload(Purchase.payments),selectinload(Purchase.branch)).where(Purchase.farmer_id==farmer_id,Purchase.status!='VOID')
    if user.role!='OWNER':
        q=q.where(Purchase.branch_id==user.branch_id)
    bills=list(db.scalars(q.order_by(Purchase.purchase_date.asc(),Purchase.id.asc()).with_for_update()))
    payable_bills=[]
    total_available=Decimal('0')
    for b in bills:
        allocated=sum((d(p.amount) for p in b.payments if p.status in ('CLEARED','PENDING')),Decimal('0'))
        unpaid=max(Decimal('0'),d(b.payable)-allocated)
        if unpaid>Decimal('0'):
            payable_bills.append((b,unpaid))
            total_available+=unpaid
    rem=d(data.amount)
    if rem>total_available:
        raise HTTPException(422,f'Payment amount (₹{inr(rem)}) exceeds total unallocated farmer balance (₹{inr(total_available)})')
    created_payments=[]
    for b,unpaid in payable_bills:
        if rem<=Decimal('0'):break
        alloc=min(rem,unpaid)
        rem-=alloc
        sub_idem=f"{data.idem_key}-{b.id}"
        existing=db.scalar(select(Payment).where(Payment.idem_key==sub_idem))
        if existing:continue
        status='CLEARED' if data.method=='CASH' else 'PENDING'
        pay=Payment(idem_key=sub_idem,purchase_id=b.id,created_by=user.id,method=data.method,status=status,amount=alloc,reference=data.reference.strip() or f"Farmer payment allocation for {b.number}",instrument_date=data.instrument_date)
        db.add(pay)
        created_payments.append({'bill':b.number,'amount':inr(alloc),'status':status})
    db.flush()
    audit(db,user,user.branch_id,'FARMER_FIFO_PAYMENT','farmer',farmer.id,f"Allocated ₹{inr(data.amount)} across {len(created_payments)} bills")
    db.commit()
    return {'ok':True,'farmer_id':farmer.id,'farmer_name':farmer.name,'total_paid':inr(data.amount),'allocations':created_payments}

@app.post('/api/purchases',status_code=201)
def add_purchase(data:PurchaseIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','PURCHASE');check_branch(user,data.branch_id)
    existing=db.scalar(select(Purchase).where(Purchase.idem_key==data.idem_key))
    if existing:
        check_branch(user,existing.branch_id)
        return {'purchase':purchase_view(existing,True),'repeated_request':True}
    
    # Point 2: Direct Farmer Resolution (existing farmer or create-on-the-fly)
    target_farmer_id = data.farmer_id
    if target_farmer_id:
        target_farmer = db.get(Farmer, target_farmer_id)
        if not target_farmer:
            raise HTTPException(422, 'Farmer not found')
    else:
        name = (data.farmer_name or '').strip()
        village = (data.farmer_village or '').strip()
        mobile = (data.farmer_mobile or '').strip()
        if not name or len(name) < 2:
            raise HTTPException(422, 'Farmer name is required (at least 2 characters)')
        if not village or len(village) < 2:
            raise HTTPException(422, 'Farmer village is required (at least 2 characters)')
        # Check if farmer with same name and village already exists
        existing_farmer = db.scalar(select(Farmer).where(func.lower(Farmer.name) == name.lower(), func.lower(Farmer.village) == village.lower()))
        if existing_farmer:
            target_farmer = existing_farmer
            if mobile and not target_farmer.mobile:
                target_farmer.mobile = mobile
        else:
            target_farmer = Farmer(name=name, village=village, mobile=mobile)
            db.add(target_farmer)
            db.flush()
            audit(db, user, data.branch_id, 'CREATE_FARMER_INLINE', 'farmer', target_farmer.id, f'{name} ({village})')
        target_farmer_id = target_farmer.id

    branch=db.get(Branch,data.branch_id)
    if not branch:raise HTTPException(422,'Factory not found')
    computed=[]
    for li in data.lines:
        gross=d(li.gross_kg,KG)
        bag_cnt=int(li.bag_count)
        bag_tare=d(li.bag_tare_kg,KG)
        bag_deduction=d(bag_cnt*bag_tare,KG)
        quality_kap=d(li.kapat_kg,KG)
        total_line_kap=bag_deduction+quality_kap
        rate=d(li.rate_per_20kg)
        if total_line_kap>=gross:
            raise HTTPException(422,'Total deductions (Bardana + Kapat) cannot equal or exceed gross weight')
        net=gross-total_line_kap
        if net<=0:
            raise HTTPException(422,'Net weight must be positive')
        val=d(net*rate/Decimal('20'))
        computed.append((li.variety.strip(),bag_cnt,bag_tare,gross,total_line_kap,net,rate,val))
    total_bags=sum((x[1] for x in computed),0)
    gross=sum((x[3] for x in computed),Decimal('0'))
    kapat=sum((x[4] for x in computed),Decimal('0'))
    net=sum((x[5] for x in computed),Decimal('0'))
    gross_value=sum((x[7] for x in computed),Decimal('0'))
    weigh=d(data.weighbridge_charges);other=d(data.other_deductions);adjust=d(data.round_adjustment)
    transport=d(data.market_transport_cost)
    payable=gross_value-weigh-other-transport+adjust
    if payable<0 or payable>MAX:raise HTTPException(422,'Invalid final payable')
    # Serialize bill numbering per branch in PostgreSQL (row-level lock).
    # SQLite is for local development only, and is not multi-factory safe.
    try:
        db.execute(select(Branch).where(Branch.id==branch.id).with_for_update()).scalar_one()
        actual_date = data.purchase_date or today()
        fyear=fy(actual_date)
        seq=db.scalar(select(BillSequence).where(BillSequence.branch_id==branch.id,BillSequence.fy==fyear))
        if not seq:
            seq=BillSequence(branch_id=branch.id,fy=fyear,last_number=0);db.add(seq);db.flush()
        seq.last_number+=1
        number=f'{branch.code}/{fyear}/{seq.last_number:06d}'
        bill=Purchase(number=number,idem_key=data.idem_key,branch_id=branch.id,farmer_id=target_farmer_id,created_by=user.id,purchase_date=actual_date,rst_number=data.rst_number.strip(),vehicle_number=data.vehicle_number.strip(),total_bags=total_bags,gross_kg=gross,kapat_kg=kapat,net_kg=net,gross_value=gross_value,weighbridge_charges=weigh,other_deductions=other,round_adjustment=adjust,payable=payable,notes=data.notes.strip(),status='POSTED',cash_paid=d(data.cash_paid),pay_later_cash=d(data.pay_later_cash),pay_later_date=data.pay_later_date,market_transport_cost=transport,unload_at_godown=bool(data.unload_at_godown))
        for variety,bc,bt,g,k,n,r,a in computed:
            mat = db.scalar(select(Material).where(func.lower(Material.name) == variety.lower()))
            mat_id = mat.id if mat else None
            bill.lines.append(PurchaseLine(variety=variety,material_id=mat_id,bag_count=bc,bag_tare_kg=bt,gross_kg=g,kapat_kg=k,net_kg=n,rate_per_20kg=r,line_amount=a))
        db.add(bill);db.flush()
        # Point 1 & 5: Auto-create payment records from bill-time settlement (single or multiple cheques)
        cheque_items = list(data.cheques) if data.cheques else []
        if not cheque_items and d(data.cheque_amount) > Decimal('0') and data.cheque_number.strip():
            cheque_items.append(ChequeIn(
                cheque_number=data.cheque_number.strip(),
                cheque_date=data.cheque_date,
                cheque_amount=data.cheque_amount
            ))

        cash_paid = d(data.cash_paid)
        total_cheques_amt = sum((d(c.cheque_amount) for c in cheque_items), Decimal('0'))
        total_settlement = cash_paid + total_cheques_amt
        if total_settlement > payable:
            raise HTTPException(422, f'Cash + cheque settlement (₹{inr(total_settlement)}) exceeds farmer payable (₹{inr(payable)})')

        if cash_paid > Decimal('0'):
            db.add(Payment(
                idem_key=f'{data.idem_key}-cash',
                purchase_id=bill.id,
                created_by=user.id,
                method='CASH',
                status='CLEARED',
                amount=cash_paid,
                reference='Cash paid on purchase',
                instrument_date=None
            ))
        for idx, chq in enumerate(cheque_items, 1):
            chq_amt = d(chq.cheque_amount)
            if chq_amt > Decimal('0') and chq.cheque_number.strip():
                db.add(Payment(
                    idem_key=f'{data.idem_key}-cheq-{idx}',
                    purchase_id=bill.id,
                    created_by=user.id,
                    method='CHEQUE',
                    status='PENDING',
                    amount=chq_amt,
                    reference=chq.cheque_number.strip(),
                    instrument_date=chq.cheque_date
                ))
        audit(db,user,branch.id,'POST_PURCHASE','purchase',bill.id,number)
        db.commit()
        loaded=db.scalar(select(Purchase).options(selectinload(Purchase.lines),selectinload(Purchase.payments),selectinload(Purchase.branch),selectinload(Purchase.farmer)).where(Purchase.id==bill.id))
        return {'purchase':purchase_view(loaded,True),'repeated_request':False}
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Purchase).where(Purchase.idem_key==data.idem_key))
        if existing:
            check_branch(user,existing.branch_id)
            return {'purchase':purchase_view(existing,True),'repeated_request':True}
        raise HTTPException(409,'Purchase conflict. Please retry with the same request key.')

@app.get('/api/purchases/next-number')
def next_purchase_number(branch_id:int,purchase_date:date|None=None,user:User=Depends(require_user),db:Session=Depends(get_db)):
    check_branch(user,branch_id)
    b=db.get(Branch,branch_id)
    if not b: raise HTTPException(404,'Branch not found')
    target_date = purchase_date or today()
    fyear = fy(target_date)
    seq = db.scalar(select(BillSequence).where(BillSequence.branch_id==branch_id,BillSequence.fy==fyear))
    next_num = (seq.last_number + 1) if seq else 1
    formatted = f'{b.code}/{fyear}/{next_num:06d}'
    return {
        'branch_id': b.id,
        'branch_code': b.code,
        'fy': fyear,
        'next_number': next_num,
        'formatted': formatted,
        'date': str(target_date)
    }

@app.get('/api/purchases')
def purchases(branch_id:int|None=None,search:str='',date_from:date|None=None,date_to:date|None=None,status:str='',limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=scoped(select(Purchase),user,Purchase).options(selectinload(Purchase.farmer),selectinload(Purchase.branch),selectinload(Purchase.payments))
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    if date_from:q=q.where(Purchase.purchase_date>=date_from)
    if date_to:q=q.where(Purchase.purchase_date<=date_to)
    if status.strip():q=q.where(Purchase.status==status.strip().upper())
    if search.strip():
        s=f'%{search.strip()}%'
        q=q.join(Farmer).where((Purchase.number.ilike(s))|(Farmer.name.ilike(s))|(Farmer.village.ilike(s))|(Farmer.mobile.ilike(s))|(Purchase.rst_number.ilike(s))|(Purchase.vehicle_number.ilike(s)))
    q=q.order_by(Purchase.id.desc()).offset(offset).limit(limit)
    return [purchase_view(x) for x in db.scalars(q)]

@app.get('/api/purchases/{purchase_id}')
def purchase_detail(purchase_id:int,user:User=Depends(require_user),db:Session=Depends(get_db)):
    p=db.scalar(select(Purchase).options(selectinload(Purchase.lines),selectinload(Purchase.payments),selectinload(Purchase.farmer),selectinload(Purchase.branch)).where(Purchase.id==purchase_id))
    if not p:raise HTTPException(404,'Purchase not found')
    check_branch(user,p.branch_id)
    return purchase_view(p,True)

@app.post('/api/purchases/{purchase_id}/void')
def void_purchase(purchase_id:int,data:PurchaseVoidIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','PURCHASE')
    p=db.scalar(select(Purchase).options(selectinload(Purchase.payments),selectinload(Purchase.lines),selectinload(Purchase.farmer),selectinload(Purchase.branch)).where(Purchase.id==purchase_id).with_for_update())
    if not p:raise HTTPException(404,'Purchase bill not found')
    check_branch(user,p.branch_id)
    if p.status=='VOID':raise HTTPException(400,'Bill is already voided')
    cleared=[pay for pay in p.payments if pay.status=='CLEARED']
    if cleared:
        raise HTTPException(400,'Cannot void bill: cleared payment(s) exist. Resolve or cancel payments first.')
    for pay in p.payments:
        if pay.status=='PENDING':
            pay.status='BOUNCED'
            pay.reference=f"{pay.reference or ''} [VOIDED: Bill cancelled]".strip()
    p.status='VOID'
    clean_reason=data.reason.strip()
    prefix=f"[VOIDED by {user.username} on {today()}: {clean_reason}]"
    p.notes=f"{p.notes}\n{prefix}" if p.notes else prefix
    audit(db,user,p.branch_id,'VOID_PURCHASE','purchase',p.id,f"{p.number}: {clean_reason}")
    db.commit()
    return purchase_view(p,True)

@app.put('/api/purchases/{purchase_id}')
def edit_purchase(purchase_id: int, data: PurchaseUpdateIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    allow(user, 'OWNER', 'PURCHASE')
    bill = db.scalar(select(Purchase).options(
        selectinload(Purchase.lines),
        selectinload(Purchase.payments),
        selectinload(Purchase.branch),
        selectinload(Purchase.farmer)
    ).where(Purchase.id == purchase_id).with_for_update())
    if not bill:
        raise HTTPException(404, 'Purchase bill not found')
    check_branch(user, bill.branch_id)
    if bill.status == 'VOID':
        raise HTTPException(400, 'Cannot edit a voided purchase bill')

    # Farmer resolution
    target_farmer_id = data.farmer_id
    if target_farmer_id:
        target_farmer = db.get(Farmer, target_farmer_id)
        if not target_farmer:
            raise HTTPException(422, 'Farmer not found')
    else:
        name = (data.farmer_name or '').strip()
        village = (data.farmer_village or '').strip()
        mobile = (data.farmer_mobile or '').strip()
        if not name or len(name) < 2:
            raise HTTPException(422, 'Farmer name is required (at least 2 characters)')
        if not village or len(village) < 2:
            raise HTTPException(422, 'Farmer village is required (at least 2 characters)')
        existing_farmer = db.scalar(select(Farmer).where(func.lower(Farmer.name) == name.lower(), func.lower(Farmer.village) == village.lower()))
        if existing_farmer:
            target_farmer = existing_farmer
            if mobile and not target_farmer.mobile:
                target_farmer.mobile = mobile
        else:
            target_farmer = Farmer(name=name, village=village, mobile=mobile)
            db.add(target_farmer)
            db.flush()
            audit(db, user, bill.branch_id, 'CREATE_FARMER_INLINE', 'farmer', target_farmer.id, f'{name} ({village})')
        target_farmer_id = target_farmer.id

    computed = []
    for li in data.lines:
        gross = d(li.gross_kg, KG)
        bag_cnt = int(li.bag_count)
        bag_tare = d(li.bag_tare_kg, KG)
        bag_deduction = d(bag_cnt * bag_tare, KG)
        quality_kap = d(li.kapat_kg, KG)
        total_line_kap = bag_deduction + quality_kap
        rate = d(li.rate_per_20kg)
        if total_line_kap >= gross:
            raise HTTPException(422, 'Total deductions (Bardana + Kapat) cannot equal or exceed gross weight')
        net = gross - total_line_kap
        if net <= 0:
            raise HTTPException(422, 'Net weight must be positive')
        val = d(net * rate / Decimal('20'))
        computed.append((li.variety.strip(), bag_cnt, bag_tare, gross, total_line_kap, net, rate, val))

    total_bags = sum((x[1] for x in computed), 0)
    gross = sum((x[3] for x in computed), Decimal('0'))
    kapat = sum((x[4] for x in computed), Decimal('0'))
    net = sum((x[5] for x in computed), Decimal('0'))
    gross_value = sum((x[7] for x in computed), Decimal('0'))
    weigh = d(data.weighbridge_charges); other = d(data.other_deductions); adjust = d(data.round_adjustment)
    transport = d(data.market_transport_cost)
    payable = gross_value - weigh - other - transport + adjust
    if payable < 0 or payable > MAX:
        raise HTTPException(422, 'Invalid final payable')

    # Update bill fields
    if data.purchase_date:
        bill.purchase_date = data.purchase_date
    bill.farmer_id = target_farmer_id
    bill.rst_number = data.rst_number.strip()
    bill.vehicle_number = data.vehicle_number.strip()
    bill.total_bags = total_bags
    bill.gross_kg = gross
    bill.kapat_kg = kapat
    bill.net_kg = net
    bill.gross_value = gross_value
    bill.weighbridge_charges = weigh
    bill.other_deductions = other
    bill.round_adjustment = adjust
    bill.market_transport_cost = transport
    bill.unload_at_godown = bool(data.unload_at_godown)
    bill.payable = payable
    bill.notes = data.notes.strip()
    bill.cash_paid = d(data.cash_paid)
    bill.pay_later_cash = d(data.pay_later_cash)
    bill.pay_later_date = data.pay_later_date

    # Replace line items
    for old_l in list(bill.lines):
        db.delete(old_l)
    bill.lines = []
    for variety, bc, bt, g, k, n, r, a in computed:
        mat = db.scalar(select(Material).where(func.lower(Material.name) == variety.lower()))
        mat_id = mat.id if mat else None
        bill.lines.append(PurchaseLine(
            purchase_id=bill.id,
            variety=variety, material_id=mat_id, bag_count=bc, bag_tare_kg=bt,
            gross_kg=g, kapat_kg=k, net_kg=n, rate_per_20kg=r, line_amount=a
        ))

    # Payment settlement update (single or multiple cheques)
    cheque_items = list(data.cheques) if data.cheques else []
    if not cheque_items and d(data.cheque_amount) > Decimal('0') and data.cheque_number.strip():
        cheque_items.append(ChequeIn(
            cheque_number=data.cheque_number.strip(),
            cheque_date=data.cheque_date,
            cheque_amount=data.cheque_amount
        ))

    cash_paid = d(data.cash_paid)
    total_cheques_amt = sum((d(c.cheque_amount) for c in cheque_items), Decimal('0'))
    total_settlement = cash_paid + total_cheques_amt
    if total_settlement > payable:
        raise HTTPException(422, f'Cash + cheque settlement (₹{inr(total_settlement)}) exceeds farmer payable (₹{inr(payable)})')

    cash_payment = next((p for p in bill.payments if p.idem_key == f'{bill.idem_key}-cash' or (p.method == 'CASH' and 'purchase' in (p.reference or '').lower())), None)
    if cash_paid > Decimal('0'):
        if cash_payment:
            cash_payment.amount = cash_paid
        else:
            new_cash = Payment(
                idem_key=f'{bill.idem_key}-cash',
                purchase_id=bill.id,
                created_by=user.id,
                method='CASH',
                status='CLEARED',
                amount=cash_paid,
                reference='Cash paid on purchase (amended)',
                instrument_date=None
            )
            bill.payments.append(new_cash)
            db.add(new_cash)
    elif cash_payment:
        if cash_payment in bill.payments:
            bill.payments.remove(cash_payment)
        db.delete(cash_payment)

    # Delete old initial cheque payments from both relationship and database
    for p in list(bill.payments):
        if p.method == 'CHEQUE' and (p.idem_key.startswith(f'{bill.idem_key}-cheq') or p.idem_key == f'{bill.idem_key}-cheq'):
            if p in bill.payments:
                bill.payments.remove(p)
            db.delete(p)
    db.flush()

    for idx, chq in enumerate(cheque_items, 1):
        amt = d(chq.cheque_amount)
        if amt > Decimal('0') and chq.cheque_number.strip():
            new_cheq = Payment(
                idem_key=f'{bill.idem_key}-cheq-{idx}-{uuid.uuid4().hex[:6]}',
                purchase_id=bill.id,
                created_by=user.id,
                method='CHEQUE',
                status='PENDING',
                amount=amt,
                reference=chq.cheque_number.strip(),
                instrument_date=chq.cheque_date
            )
            bill.payments.append(new_cheq)
            db.add(new_cheq)

    audit(db, user, bill.branch_id, 'EDIT_PURCHASE', 'purchase', bill.id, f'Amended bill {bill.number}')
    db.commit()
    loaded = db.scalar(select(Purchase).options(
        selectinload(Purchase.lines),
        selectinload(Purchase.payments),
        selectinload(Purchase.branch),
        selectinload(Purchase.farmer)
    ).where(Purchase.id == bill.id))
    return {'purchase': purchase_view(loaded, True), 'ok': True}

@app.post('/api/purchases/{purchase_id}/payments',status_code=201)
def add_payment(purchase_id:int,data:PaymentIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','ACCOUNTS')
    pay=db.scalar(select(Payment).where(Payment.idem_key==data.idem_key))
    if pay:
        p=db.get(Purchase,pay.purchase_id);check_branch(user,p.branch_id)
        return {'payment':payment_view(pay),'repeated_request':True}
    p=db.scalar(select(Purchase).options(selectinload(Purchase.payments)).where(Purchase.id==purchase_id).with_for_update())
    if not p:raise HTTPException(404,'Bill not found')
    check_branch(user,p.branch_id)
    if p.status!='POSTED':raise HTTPException(409,'Bill not active')
    amt=d(data.amount)
    active=sum((d(x.amount) for x in p.payments if x.status!='BOUNCED'),Decimal('0'))
    if active+amt>d(p.payable):raise HTTPException(422,'Payment allocation exceeds remaining payable')
    if data.method in ('CHEQUE','BANK') and not data.reference.strip():raise HTTPException(422,'Cheque/bank reference is required')
    status='CLEARED' if data.method=='CASH' else 'PENDING'
    pay=Payment(idem_key=data.idem_key,purchase_id=p.id,created_by=user.id,method=data.method,status=status,amount=amt,reference=data.reference.strip(),instrument_date=data.instrument_date)
    db.add(pay);db.flush();audit(db,user,p.branch_id,'CREATE_PAYMENT','payment',pay.id,f'{data.method} {inr(amt)} {status}')
    db.commit()
    return {'payment':payment_view(pay),'repeated_request':False}

@app.post('/api/payments/{payment_id}/status')
def change_payment(payment_id:int,data:PaymentStatusIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','ACCOUNTS')
    p=db.scalar(select(Payment).where(Payment.id==payment_id).with_for_update())
    if not p:raise HTTPException(404,'Payment not found')
    bill=db.get(Purchase,p.purchase_id);check_branch(user,bill.branch_id)
    if p.status!='PENDING':raise HTTPException(409,'Only pending payment instruments can be finalized')
    if p.method=='CASH':raise HTTPException(409,'Cash payments are cleared at recording')
    p.status=data.status
    audit(db,user,bill.branch_id,'PAYMENT_STATUS','payment',p.id,data.status)
    db.commit()
    return {'payment':payment_view(p)}

# Point 7: Batch status update for inline cheque clearing register
@app.post('/api/payments/batch-status')
def batch_change_payments(data:BatchPaymentStatusIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','ACCOUNTS')
    updated=[]
    for it in data.items:
        p=db.scalar(select(Payment).where(Payment.id==it.payment_id).with_for_update())
        if not p: continue
        bill=db.get(Purchase,p.purchase_id)
        if not bill: continue
        if user.role!='OWNER' and bill.branch_id!=user.branch_id: continue
        if p.status!=it.status:
            p.status=it.status
            if it.clearance_date:
                p.instrument_date=it.clearance_date
            audit(db,user,bill.branch_id,'BATCH_PAYMENT_STATUS','payment',p.id,f'status={it.status}')
            updated.append(p.id)
    db.commit()
    return {'ok':True,'updated_count':len(updated),'updated_ids':updated}

@app.get('/api/payments/pending-count')
def pending_cheques_count(branch_id: int | None = None, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if branch_id:
        check_branch(user, branch_id)
    q = scoped(select(func.count(Payment.id)).join(Payment.purchase).where(
        Payment.status == 'PENDING',
        Payment.method == 'CHEQUE',
        Purchase.status != 'VOID'
    ), user, Purchase)
    if branch_id:
        q = q.where(Purchase.branch_id == branch_id)
    count = db.scalar(q) or 0
    return {'pending_count': count}

@app.get('/api/payments')
def payments(branch_id:int|None=None,status:str='',month:str='',user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=select(Payment).join(Purchase,Payment.purchase_id==Purchase.id).options(selectinload(Payment.purchase).selectinload(Purchase.farmer)).order_by(Payment.id.desc()).limit(1000)
    if user.role!='OWNER':q=q.where(Purchase.branch_id==user.branch_id)
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    if status:q=q.where(Payment.status==status)
    if month.strip():
        # month format: YYYY-MM
        try:
            yr, mo = [int(x) for x in month.strip().split('-')[:2]]
            # Filter by purchase_date or instrument_date in that month
            start_d = date(yr, mo, 1)
            end_d = date(yr + 1, 1, 1) if mo == 12 else date(yr, mo + 1, 1)
            q=q.where((Purchase.purchase_date >= start_d) & (Purchase.purchase_date < end_d))
        except Exception:
            pass
    return [payment_view(p) for p in db.scalars(q)]

@app.get('/api/dashboard')
def dashboard(branch_id:int|None=None,user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=scoped(select(Purchase).where(Purchase.status!='VOID'),user,Purchase).options(selectinload(Purchase.payments))
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    bills=list(db.scalars(q))
    daily=[x for x in bills if x.purchase_date==today()]
    return {'date':str(today()),'today_bills':len(daily),'today_kg':kg(sum((d(x.net_kg,KG) for x in daily),Decimal('0'))),'today_value':inr(sum((d(x.payable) for x in daily),Decimal('0'))),'all_bills':len(bills),'all_kg':kg(sum((d(x.net_kg,KG) for x in bills),Decimal('0'))),'total_purchase_value':inr(sum((d(x.payable) for x in bills),Decimal('0'))),'outstanding':inr(sum((Decimal(pay_summary(x)['outstanding']) for x in bills),Decimal('0'))),'pending_instruments':inr(sum((Decimal(pay_summary(x)['pending']) for x in bills),Decimal('0')))}

@app.get('/api/export/purchases')
def export_purchases(branch_id:int|None=None,user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=scoped(select(Purchase),user,Purchase).options(selectinload(Purchase.farmer),selectinload(Purchase.branch),selectinload(Purchase.payments)).order_by(Purchase.id)
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['Bill','Date','Factory','Farmer','Village','Mobile','RST','Net kg','Gross value INR','Charges INR','Adjustments INR','Payable INR','Cleared INR','Pending INR','Outstanding INR','Status'])
    def safe(s):
        s=str(s)
        return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s
    for x in db.scalars(q):
        ps=pay_summary(x)
        writer.writerow([safe(x.number),x.purchase_date,safe(x.branch.name),safe(x.farmer.name),safe(x.farmer.village),safe(x.farmer.mobile),safe(x.rst_number),kg(x.net_kg),inr(x.gross_value),inr(x.weighbridge_charges+x.other_deductions),inr(x.round_adjustment),inr(x.payable),ps['cleared'],ps['pending'],ps['outstanding'],safe(x.status)])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="Farmkart_Purchases.csv"'})

@app.get('/api/audit')
def audits(limit:int=Query(100,ge=1,le=500),user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    entries=db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limit))
    return [{'id':x.id,'user_id':x.user_id,'branch_id':x.branch_id,'action':x.action,'entity':x.entity,'entity_id':x.entity_id,'details':x.details,'at':str(x.created_at)} for x in entries]

@app.get('/api/users')
def list_users(user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    q=select(User).options(selectinload(User.branch)).order_by(User.id)
    return [{
        'id':u.id,
        'username':u.username,
        'name':u.full_name,
        'role':u.role,
        'branch_id':u.branch_id,
        'branch_name':u.branch.name if u.branch else 'All factories (Owner)',
        'branch_code':u.branch.code if u.branch else 'ALL',
        'active':u.active
    } for u in db.scalars(q)]

@app.post('/api/users',status_code=201)
def create_user_endpoint(data:UserCreateIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    clean_username=data.username.strip().lower()
    if not clean_username.isalnum() and not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_.-' for c in clean_username):
        raise HTTPException(422,'Username may only contain letters, numbers, dots, hyphens and underscores')
    if db.scalar(select(User).where(User.username==clean_username)):
        raise HTTPException(409,'Username already exists')
    if data.role!='OWNER':
        if not data.branch_id:
            raise HTTPException(422,'A factory must be assigned for staff roles')
        if not db.get(Branch,data.branch_id):
            raise HTTPException(422,'Assigned factory does not exist')
        target_branch=data.branch_id
    else:
        target_branch=None
    new_user=User(
        username=clean_username,
        full_name=data.name.strip(),
        password_hash=encode_password(data.password),
        role=data.role,
        branch_id=target_branch,
        active=True
    )
    db.add(new_user)
    db.flush()
    audit(db,user,target_branch,'CREATE_USER','user',new_user.id,f'{clean_username} ({data.role})')
    db.commit()
    loaded=db.scalar(select(User).options(selectinload(User.branch)).where(User.id==new_user.id))
    return {
        'id':loaded.id,
        'username':loaded.username,
        'name':loaded.full_name,
        'role':loaded.role,
        'branch_id':loaded.branch_id,
        'branch_name':loaded.branch.name if loaded.branch else 'All factories (Owner)',
        'active':loaded.active
    }

@app.patch('/api/users/{user_id}/status')
def update_user_status(user_id:int,data:UserStatusIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    target=db.get(User,user_id)
    if not target:raise HTTPException(404,'User not found')
    if target.id==user.id and not data.active:
        raise HTTPException(400,'You cannot deactivate your own account')
    target.active=data.active
    if not data.active:
        active_tokens=db.scalars(select(SessionToken).where(SessionToken.user_id==target.id)).all()
        for tok in active_tokens:
            db.delete(tok)
    audit(db,user,target.branch_id,'USER_STATUS','user',target.id,f'active={data.active}')
    db.commit()
    return {'id':target.id,'active':target.active}

@app.post('/api/users/{user_id}/reset-password')
def reset_user_password(user_id:int,data:UserResetPasswordIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    target=db.get(User,user_id)
    if not target:raise HTTPException(404,'User not found')
    target.password_hash=encode_password(data.new_password)
    active_tokens=db.scalars(select(SessionToken).where(SessionToken.user_id==target.id)).all()
    for tok in active_tokens:
        db.delete(tok)
    audit(db,user,target.branch_id,'RESET_PASSWORD','user',target.id,f'Reset password for {target.username}')
    db.commit()
    return {'ok':True,'message':f'Password updated for {target.username}'}
