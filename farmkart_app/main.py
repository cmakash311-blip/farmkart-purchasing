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
from .models import Branch, User, SessionToken, Farmer, BillSequence, Purchase, PurchaseLine, Payment, Audit
from .security import COOKIE_NAME, hash_token, check_password, new_session, require_user, check_branch, allow, can_access

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
    cleared=sum((d(p.amount) for p in bill.payments if p.status=='CLEARED'),Decimal('0'))
    pending=sum((d(p.amount) for p in bill.payments if p.status=='PENDING'),Decimal('0'))
    return {'cleared':inr(cleared),'pending':inr(pending),'outstanding':inr(max(Decimal('0'),d(bill.payable)-cleared)), 'unallocated':inr(max(Decimal('0'),d(bill.payable)-cleared-pending))}

def purchase_view(p:Purchase,detail=False):
    data={'id':p.id,'number':p.number,'date':str(p.purchase_date),'branch_id':p.branch_id,'branch':p.branch.name,'farmer_id':p.farmer_id,'farmer':p.farmer.name,'village':p.farmer.village,'mobile':p.farmer.mobile,'rst':p.rst_number,'vehicle':p.vehicle_number,'gross_kg':kg(p.gross_kg),'kapat_kg':kg(p.kapat_kg),'net_kg':kg(p.net_kg),'gross_value':inr(p.gross_value),'weighbridge_charges':inr(p.weighbridge_charges),'other_deductions':inr(p.other_deductions),'round_adjustment':inr(p.round_adjustment),'payable':inr(p.payable),'status':p.status,'notes':p.notes,'payments_summary':pay_summary(p)}
    if detail:
        data['lines']=[{'variety':x.variety,'gross_kg':kg(x.gross_kg),'kapat_kg':kg(x.kapat_kg),'net_kg':kg(x.net_kg),'rate_per_20kg':inr(x.rate_per_20kg),'amount':inr(x.line_amount)} for x in p.lines]
        data['payments']=[payment_view(x,p.number,p.farmer.name,p.branch_id) for x in p.payments]
    return data

def payment_view(p:Payment, bill_number=None, farmer=None, branch_id=None):
    return {'id':p.id,'purchase_id':p.purchase_id,'bill_number':bill_number or p.purchase.number,'farmer':farmer or p.purchase.farmer.name,'branch_id':branch_id or p.purchase.branch_id,'method':p.method,'status':p.status,'amount':inr(p.amount),'reference':p.reference,'instrument_date':str(p.instrument_date or ''),'created_at':str(p.created_at)}

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

class LineIn(BaseModel):
    variety:str=Field(min_length=2,max_length=80)
    gross_kg:Decimal=Field(gt=0,le=10000000)
    kapat_kg:Decimal=Field(ge=0,le=10000000)
    rate_per_20kg:Decimal=Field(gt=0,le=10000000)

class PurchaseIn(BaseModel):
    idem_key: str=Field(min_length=16,max_length=100)
    branch_id:int
    farmer_id:int
    rst_number:str=Field(default='',max_length=80)
    vehicle_number:str=Field(default='',max_length=60)
    weighbridge_charges:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    other_deductions:Decimal=Field(default=Decimal('0'),ge=0,le=10000000)
    round_adjustment:Decimal=Field(default=Decimal('0'),ge=-10000000,le=10000000)
    notes:str=Field(default='',max_length=1000)
    lines:list[LineIn]=Field(min_length=1,max_length=25)

class PaymentIn(BaseModel):
    idem_key:str=Field(min_length=16,max_length=100)
    method:Literal['CASH','CHEQUE','BANK']
    amount:Decimal=Field(gt=0,le=1000000000)
    reference:str=Field(default='',max_length=100)
    instrument_date:date|None=None

class PaymentStatusIn(BaseModel):
    status:Literal['CLEARED','BOUNCED']

@app.get('/')
def index(): return FileResponse(STATIC/'index.html')

@app.get('/static/{filename}')
def static(filename:str):
    if filename not in ['app.css','app.js']: raise HTTPException(404)
    return FileResponse(STATIC/filename)

@app.get('/api/health')
def health(): return {'status':'ok'}

@app.post('/api/login')
def login(data:LoginIn, response:Response, db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.username==data.username.strip().lower()))
    if not user or not user.active or not check_password(data.password,user.password_hash):
        raise HTTPException(401,'Incorrect username or password')
    token, record = new_session(db,user)
    secure=os.getenv('COOKIE_SECURE','0')=='1'
    response.set_cookie(COOKIE_NAME,token,httponly=True,secure=secure,samesite='strict',max_age=12*3600,path='/')
    return {'ok':True,'csrf_token':record.csrf_token}

@app.post('/api/logout')
def logout(request:Request,response:Response,user:User=Depends(require_user), db:Session=Depends(get_db)):
    token=request.cookies.get(COOKIE_NAME,'')
    row=db.scalar(select(SessionToken).where(SessionToken.token_hash==hash_token(token)))
    if row: db.delete(row);db.commit()
    response.delete_cookie(COOKIE_NAME,path='/')
    return {'ok':True}

@app.get('/api/me')
def me(request:Request,user:User=Depends(require_user),db:Session=Depends(get_db)):
    token=request.cookies.get(COOKIE_NAME,'')
    row=db.scalar(select(SessionToken).where(SessionToken.token_hash==hash_token(token)))
    return {'id':user.id,'name':user.full_name,'username':user.username,'role':user.role,'branch_id':user.branch_id,'csrf_token':row.csrf_token}

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

@app.post('/api/purchases',status_code=201)
def add_purchase(data:PurchaseIn,user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER','PURCHASE');check_branch(user,data.branch_id)
    existing=db.scalar(select(Purchase).where(Purchase.idem_key==data.idem_key))
    if existing:
        check_branch(user,existing.branch_id)
        return {'purchase':purchase_view(existing,True),'repeated_request':True}
    if not db.get(Farmer,data.farmer_id):raise HTTPException(422,'Farmer not found')
    branch=db.get(Branch,data.branch_id)
    if not branch:raise HTTPException(422,'Factory not found')
    computed=[]
    for li in data.lines:
        gross=d(li.gross_kg,KG);kap=d(li.kapat_kg,KG);rate=d(li.rate_per_20kg)
        if kap>gross:raise HTTPException(422,'Kapat cannot exceed gross weight')
        net=gross-kap
        if net<=0:raise HTTPException(422,'Net weight must be positive')
        val=d(net*rate/Decimal('20'))
        computed.append((li.variety.strip(),gross,kap,net,rate,val))
    gross=sum((x[1] for x in computed),Decimal('0'));kapat=sum((x[2] for x in computed),Decimal('0'))
    net=sum((x[3] for x in computed),Decimal('0'));gross_value=sum((x[5] for x in computed),Decimal('0'))
    weigh=d(data.weighbridge_charges);other=d(data.other_deductions);adjust=d(data.round_adjustment)
    payable=gross_value-weigh-other+adjust
    if payable<0 or payable>MAX:raise HTTPException(422,'Invalid final payable')
    # Serialize bill numbering per branch in PostgreSQL (row-level lock).
    # SQLite is for local development only, and is not multi-factory safe.
    try:
        db.execute(select(Branch).where(Branch.id==branch.id).with_for_update()).scalar_one()
        fyear=fy(today())
        seq=db.scalar(select(BillSequence).where(BillSequence.branch_id==branch.id,BillSequence.fy==fyear))
        if not seq:
            seq=BillSequence(branch_id=branch.id,fy=fyear,last_number=0);db.add(seq);db.flush()
        seq.last_number+=1
        number=f'{branch.code}/{fyear}/{seq.last_number:06d}'
        bill=Purchase(number=number,idem_key=data.idem_key,branch_id=branch.id,farmer_id=data.farmer_id,created_by=user.id,purchase_date=today(),rst_number=data.rst_number.strip(),vehicle_number=data.vehicle_number.strip(),gross_kg=gross,kapat_kg=kapat,net_kg=net,gross_value=gross_value,weighbridge_charges=weigh,other_deductions=other,round_adjustment=adjust,payable=payable,notes=data.notes.strip(),status='POSTED')
        for variety,g,k,n,r,a in computed:
            bill.lines.append(PurchaseLine(variety=variety,gross_kg=g,kapat_kg=k,net_kg=n,rate_per_20kg=r,line_amount=a))
        db.add(bill);db.flush()
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

@app.get('/api/purchases')
def purchases(branch_id:int|None=None,search:str='',date_from:date|None=None,date_to:date|None=None,limit:int=Query(200,ge=1,le=1000),user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=scoped(select(Purchase),user,Purchase).options(selectinload(Purchase.farmer),selectinload(Purchase.branch),selectinload(Purchase.payments))
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    if date_from:q=q.where(Purchase.purchase_date>=date_from)
    if date_to:q=q.where(Purchase.purchase_date<=date_to)
    if search.strip():
        s=f'%{search.strip()}%'
        q=q.join(Farmer).where((Purchase.number.ilike(s))|(Farmer.name.ilike(s))|(Farmer.village.ilike(s))|(Purchase.rst_number.ilike(s)))
    q=q.order_by(Purchase.id.desc()).limit(limit)
    return [purchase_view(x) for x in db.scalars(q)]

@app.get('/api/purchases/{purchase_id}')
def purchase_detail(purchase_id:int,user:User=Depends(require_user),db:Session=Depends(get_db)):
    p=db.scalar(select(Purchase).options(selectinload(Purchase.lines),selectinload(Purchase.payments),selectinload(Purchase.farmer),selectinload(Purchase.branch)).where(Purchase.id==purchase_id))
    if not p:raise HTTPException(404,'Purchase not found')
    check_branch(user,p.branch_id)
    return purchase_view(p,True)

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

@app.get('/api/payments')
def payments(branch_id:int|None=None,status:str='',user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=select(Payment).join(Purchase,Payment.purchase_id==Purchase.id).options(selectinload(Payment.purchase).selectinload(Purchase.farmer)).order_by(Payment.id.desc()).limit(500)
    if user.role!='OWNER':q=q.where(Purchase.branch_id==user.branch_id)
    if branch_id:q=q.where(Purchase.branch_id==branch_id)
    if status:q=q.where(Payment.status==status)
    return [payment_view(p) for p in db.scalars(q)]

@app.get('/api/dashboard')
def dashboard(branch_id:int|None=None,user:User=Depends(require_user),db:Session=Depends(get_db)):
    if branch_id:check_branch(user,branch_id)
    q=scoped(select(Purchase),user,Purchase).options(selectinload(Purchase.payments))
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
    writer.writerow(['Bill','Date','Factory','Farmer','Village','Mobile','RST','Net kg','Gross value INR','Charges INR','Adjustments INR','Payable INR','Cleared INR','Pending INR','Outstanding INR'])
    def safe(s):
        s=str(s)
        return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s
    for x in db.scalars(q):
        ps=pay_summary(x)
        writer.writerow([safe(x.number),x.purchase_date,safe(x.branch.name),safe(x.farmer.name),safe(x.farmer.village),safe(x.farmer.mobile),safe(x.rst_number),kg(x.net_kg),inr(x.gross_value),inr(x.weighbridge_charges+x.other_deductions),inr(x.round_adjustment),inr(x.payable),ps['cleared'],ps['pending'],ps['outstanding']])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="Farmkart_Purchases.csv"'})

@app.get('/api/audit')
def audits(limit:int=Query(100,ge=1,le=500),user:User=Depends(require_user),db:Session=Depends(get_db)):
    allow(user,'OWNER')
    entries=db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limit))
    return [{'id':x.id,'user_id':x.user_id,'branch_id':x.branch_id,'action':x.action,'entity':x.entity,'entity_id':x.entity_id,'details':x.details,'at':str(x.created_at)} for x in entries]
