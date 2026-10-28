import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from farmkart_app.db import Base, get_db
from farmkart_app.main import app
from farmkart_app.models import Branch, User
from farmkart_app.security import encode_password

@pytest.fixture
def setup():
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session=sessionmaker(bind=eng,expire_on_commit=False)
    with Session.begin() as db:
        db.add_all([Branch(id=1,code='HMT',name='Himatnagar'),Branch(id=2,code='MDS',name='Modasa')])
        db.add_all([
            User(username='owner',full_name='Owner',password_hash=encode_password('VeryStrongPass#123'),role='OWNER',branch_id=None),
            User(username='hmtbuy',full_name='HMT Buyer',password_hash=encode_password('VeryStrongPass#123'),role='PURCHASE',branch_id=1),
            User(username='hmtacct',full_name='HMT Accountant',password_hash=encode_password('VeryStrongPass#123'),role='ACCOUNTS',branch_id=1),
            User(username='mdsbuy',full_name='MDS Buyer',password_hash=encode_password('VeryStrongPass#123'),role='PURCHASE',branch_id=2),
        ])
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear();eng.dispose()

def auth(c,name):
    result=c.post('/api/login',json={'username':name,'password':'VeryStrongPass#123'})
    assert result.status_code==200,result.text
    return {'X-CSRF-Token':result.json()['csrf_token']}

def farmer(c,h):
    r=c.post('/api/farmers',headers=h,json={'name':'Sample Farmer','village':'Example Village','mobile':'9000000000','cooperative':'54 Coop'})
    assert r.status_code==201,r.text
    return r.json()['id']

def bill(c,h,farmer_id,branch=1,idem=None):
    return c.post('/api/purchases',headers=h,json={'branch_id':branch,'farmer_id':farmer_id,'idem_key':idem or uuid.uuid4().hex,'rst_number':'RST-A','weighbridge_charges':'20.00','other_deductions':'0','round_adjustment':'0', 'lines':[{'variety':'Java','gross_kg':'1000','kapat_kg':'0','rate_per_20kg':'2200'}]})

def test_login_and_csrf(setup):
    c=setup
    assert c.get('/api/me').status_code==401
    wrong=c.post('/api/login',json={'username':'owner','password':'wrong'})
    assert wrong.status_code==401
    login_resp=c.post('/api/login',json={'username':'owner','password':'VeryStrongPass#123'})
    assert login_resp.status_code==200
    token=login_resp.json().get('token')
    assert token and len(token) > 20
    # Test Bearer token access on a new client instance without cookies
    with TestClient(app) as bearer_client:
        assert bearer_client.get('/api/me').status_code==401
        bearer_me=bearer_client.get('/api/me',headers={'Authorization':f'Bearer {token}'})
        assert bearer_me.status_code==200
        assert bearer_me.json()['username']=='owner'
    h=auth(c,'owner')
    assert c.get('/api/me').status_code==200
    assert c.post('/api/farmers',json={'name':'N','village':'G'}).status_code==403
    assert c.get('/').status_code==200
    assert c.get('/static/app.js').status_code==200
    assert c.get('/static/../../etc/passwd').status_code!=200

def test_purchase_total_and_idempotency(setup):
    c=setup;h=auth(c,'owner');fid=farmer(c,h)
    idem=uuid.uuid4().hex
    r=bill(c,h,fid,1,idem)
    assert r.status_code==201,r.text
    p=r.json()['purchase'];assert p['number'].startswith('HMT/')
    assert p['net_kg']=='1000.000' and p['gross_value']=='110000.00' and p['payable']=='109980.00'
    assert p['payments_summary']['outstanding']=='109980.00'
    r2=bill(c,h,fid,1,idem)
    assert r2.status_code==201,r2.text
    assert r2.json()['repeated_request'] is True
    assert r2.json()['purchase']['number']==p['number']
    r3=bill(c,h,fid,2)
    assert r3.status_code==201 and r3.json()['purchase']['number'].startswith('MDS/')
    assert c.get('/api/dashboard').json()['all_bills']==2
    assert c.get('/api/dashboard?branch_id=1').json()['all_bills']==1

def test_branch_security_and_payments(setup):
    c=setup;h=auth(c,'owner');fid=farmer(c,h);p=bill(c,h,fid,1).json()['purchase']
    r=c.post(f"/api/purchases/{p['id']}/payments",headers=h,json={'idem_key':uuid.uuid4().hex,'method':'CHEQUE','amount':'50000','reference':'CHK123'})
    assert r.status_code==201,r.text
    pay=r.json()['payment'];assert pay['status']=='PENDING'
    detail=c.get(f"/api/purchases/{p['id']}").json()
    assert detail['payments_summary']['outstanding']=='109980.00'
    assert detail['payments_summary']['unallocated']=='59980.00'
    r=c.post(f"/api/payments/{pay['id']}/status",headers=h,json={'status':'CLEARED'})
    assert r.status_code==200,r.text
    assert c.get(f"/api/purchases/{p['id']}").json()['payments_summary']['outstanding']=='59980.00'
    o=c.post(f"/api/purchases/{p['id']}/payments",headers=h,json={'idem_key':uuid.uuid4().hex,'method':'CASH','amount':'59981'})
    assert o.status_code==422
    auth(c,'mdsbuy')
    assert c.get(f"/api/purchases/{p['id']}").status_code==403
    assert c.get('/api/purchases').json()==[]
    assert c.get('/api/payments').json()==[]
    assert c.get('/api/dashboard?branch_id=1').status_code==403
    assert c.get('/api/audit').status_code==403
    mismatch=bill(c,{'X-CSRF-Token':c.get('/api/me').json()['csrf_token']},fid,branch=1)
    assert mismatch.status_code==403

def test_validation(setup):
    c=setup;h=auth(c,'owner');fid=farmer(c,h)
    r=c.post('/api/purchases',headers=h,json={'branch_id':1,'farmer_id':fid,'idem_key':uuid.uuid4().hex,'lines':[{'variety':'Bold','gross_kg':'10','kapat_kg':'12','rate_per_20kg':'2000'}]})
    assert r.status_code==422
    assert c.get('/api/dashboard').json()['all_bills']==0

def test_user_management(setup):
    c=setup
    # Non-owner forbidden
    auth(c,'hmtbuy')
    assert c.get('/api/users').status_code==403
    assert c.post('/api/users',json={'username':'newuser','name':'New','role':'PURCHASE','password':'Password12345!'}).status_code==403
    
    # Owner access
    h=auth(c,'owner')
    users=c.get('/api/users').json()
    assert len(users)>=4
    assert any(u['username']=='owner' and u['role']=='OWNER' for u in users)
    
    # Validation failures
    # 1. Password too short (<12 chars)
    short_pwd=c.post('/api/users',headers=h,json={'username':'clerk1','name':'Clerk One','role':'PURCHASE','branch_id':1,'password':'short'})
    assert short_pwd.status_code==422
    
    # 2. Staff role without branch
    no_branch=c.post('/api/users',headers=h,json={'username':'clerk1','name':'Clerk One','role':'PURCHASE','password':'ValidPassword@123'})
    assert no_branch.status_code==422
    
    # 3. Create staff user successfully
    created=c.post('/api/users',headers=h,json={'username':'clerk1','name':'Clerk One','role':'PURCHASE','branch_id':1,'password':'ValidPassword@123'})
    assert created.status_code==201, created.text
    user_data=created.json()
    assert user_data['username']=='clerk1'
    assert user_data['role']=='PURCHASE'
    assert user_data['branch_id']==1
    assert user_data['active'] is True
    
    # 4. Duplicate username rejected
    dup=c.post('/api/users',headers=h,json={'username':'clerk1','name':'Another Clerk','role':'PURCHASE','branch_id':1,'password':'ValidPassword@123'})
    assert dup.status_code==409
    
    # 5. New user can log in
    login_res=c.post('/api/login',json={'username':'clerk1','password':'ValidPassword@123'})
    assert login_res.status_code==200, login_res.text
    clerk_csrf={'X-CSRF-Token':login_res.json()['csrf_token']}
    me=c.get('/api/me',headers=clerk_csrf).json()
    assert me['username']=='clerk1'
    assert me['role']=='PURCHASE'
    assert me['branch_id']==1
    
    # 6. Owner deactivates user
    h=auth(c,'owner')
    # Self-deactivation forbidden
    owner_id=[u['id'] for u in c.get('/api/users').json() if u['username']=='owner'][0]
    self_deact=c.patch(f'/api/users/{owner_id}/status',headers=h,json={'active':False})
    assert self_deact.status_code==400
    
    deact=c.patch(f"/api/users/{user_data['id']}/status",headers=h,json={'active':False})
    assert deact.status_code==200
    assert deact.json()['active'] is False
    
    # Deactivated user cannot log in
    assert c.post('/api/login',json={'username':'clerk1','password':'ValidPassword@123'}).status_code==401
    
    # 7. Owner reactivates user and resets password
    react=c.patch(f"/api/users/{user_data['id']}/status",headers=h,json={'active':True})
    assert react.status_code==200
    assert react.json()['active'] is True
    
    reset=c.post(f"/api/users/{user_data['id']}/reset-password",headers=h,json={'new_password':'NewStrongPassword@999'})
    assert reset.status_code==200
    
    # Old password fails
    assert c.post('/api/login',json={'username':'clerk1','password':'ValidPassword@123'}).status_code==401
    # New password succeeds
    assert c.post('/api/login',json={'username':'clerk1','password':'NewStrongPassword@999'}).status_code==200

def test_void_purchase_bill(setup):
    c=setup
    h=auth(c,'owner')
    fid=farmer(c,h)
    
    # 1. Create a bill
    res=bill(c,h,fid,branch=1).json()['purchase']
    bill_id=res['id']
    assert res['status']=='POSTED'
    assert c.get('/api/dashboard?branch_id=1').json()['all_bills']==1
    
    # 2. Short reason rejected (<5 chars)
    short_void=c.post(f'/api/purchases/{bill_id}/void',headers=h,json={'reason':'bad'})
    assert short_void.status_code==422
    
    # 3. Add a pending cheque
    pay_res=c.post(f"/api/purchases/{bill_id}/payments",headers=h,json={
        'idem_key':uuid.uuid4().hex,
        'method':'CHEQUE',
        'amount':'20000',
        'reference':'CHQ-TEST-001'
    })
    assert pay_res.status_code==201
    pay_id=pay_res.json()['payment']['id']
    assert pay_res.json()['payment']['status']=='PENDING'
    
    # 4. Void the bill with valid reason
    void_res=c.post(f'/api/purchases/{bill_id}/void',headers=h,json={'reason':'Operator entered wrong tare weight on ticket'})
    assert void_res.status_code==200, void_res.text
    voided_data=void_res.json()
    assert voided_data['status']=='VOID'
    assert 'Operator entered wrong tare weight' in voided_data['notes']
    assert voided_data['payments_summary']['outstanding']=='0.00'
    assert voided_data['payments_summary']['unallocated']=='0.00'
    
    # Pending cheque is now cancelled/bounced
    payments=c.get(f'/api/purchases/{bill_id}').json()['payments']
    assert payments[0]['status']=='BOUNCED'
    
    # 5. Dashboard excludes voided bill
    dash=c.get('/api/dashboard?branch_id=1').json()
    assert dash['all_bills']==0
    assert dash['today_bills']==0
    assert dash['all_kg']=='0.000'
    assert dash['total_purchase_value']=='0.00'
    
    # 6. Cannot add payments to a voided bill
    pay_after_void=c.post(f"/api/purchases/{bill_id}/payments",headers=h,json={
        'idem_key':uuid.uuid4().hex,
        'method':'CASH',
        'amount':'5000'
    })
    assert pay_after_void.status_code==409
    
    # 7. Cannot void already voided bill
    dup_void=c.post(f'/api/purchases/{bill_id}/void',headers=h,json={'reason':'Trying again'})
    assert dup_void.status_code==400
    
    # 8. Cannot void a bill with cleared payments
    res2=bill(c,h,fid,branch=1).json()['purchase']
    b2_id=res2['id']
    # Add cash payment (which clears instantly)
    c.post(f"/api/purchases/{b2_id}/payments",headers=h,json={
        'idem_key':uuid.uuid4().hex,
        'method':'CASH',
        'amount':'10000'
    })
    void_cleared=c.post(f'/api/purchases/{b2_id}/void',headers=h,json={'reason':'Mistake made but cash already given'})
    assert void_cleared.status_code==400
    assert 'cleared payment' in void_cleared.json()['detail']

def test_purchase_search_and_date_filtering(setup):
    c=setup
    h=auth(c,'owner')
    f1=c.post('/api/farmers',headers=h,json={'name':'Ramesh Patel','village':'Gambhoi','mobile':'9825000001'}).json()['id']
    f2=c.post('/api/farmers',headers=h,json={'name':'Suresh Shah','village':'Tintoi','mobile':'9825000002'}).json()['id']
    
    b1=c.post('/api/purchases',headers=h,json={
        'branch_id':1,'farmer_id':f1,'idem_key':uuid.uuid4().hex,
        'rst_number':'RST-101','vehicle_number':'GJ-09-AB-1234',
        'lines':[{'variety':'Java','gross_kg':'1000','kapat_kg':'0','rate_per_20kg':'2200'}]
    }).json()['purchase']
    
    b2=c.post('/api/purchases',headers=h,json={
        'branch_id':1,'farmer_id':f2,'idem_key':uuid.uuid4().hex,
        'rst_number':'RST-202','vehicle_number':'GJ-01-XY-9999',
        'lines':[{'variety':'Bold','gross_kg':'2000','kapat_kg':'10','rate_per_20kg':'2100'}]
    }).json()['purchase']
    
    # 1. Search by vehicle number
    s_veh=c.get('/api/purchases?search=AB-1234').json()
    assert len(s_veh)==1
    assert s_veh[0]['id']==b1['id']
    
    # 2. Search by RST
    s_rst=c.get('/api/purchases?search=RST-202').json()
    assert len(s_rst)==1
    assert s_rst[0]['id']==b2['id']
    
    # 3. Search by farmer mobile
    s_mob=c.get('/api/purchases?search=9825000001').json()
    assert len(s_mob)==1
    assert s_mob[0]['id']==b1['id']
    
    # 4. Filter by status
    c.post(f"/api/purchases/{b1['id']}/void",headers=h,json={'reason':'Void for search test'})
    s_void=c.get('/api/purchases?status=VOID').json()
    assert any(x['id']==b1['id'] for x in s_void)
    assert not any(x['id']==b2['id'] for x in s_void)
    
    s_post=c.get('/api/purchases?status=POSTED').json()
    assert any(x['id']==b2['id'] for x in s_post)
    assert not any(x['id']==b1['id'] for x in s_post)
    
    # 5. Pagination with limit and offset
    page1=c.get('/api/purchases?limit=1&offset=0').json()
    assert len(page1)==1
    page2=c.get('/api/purchases?limit=1&offset=1').json()
    assert len(page2)==1
    assert page1[0]['id']!=page2[0]['id']
    
    # 6. Future date filter returns empty
    future=c.get('/api/purchases?date_from=2099-01-01').json()
    assert future==[]

def test_gunny_bag_and_bardana_calculation(setup):
    c=setup
    h=auth(c,'owner')
    fid=farmer(c,h)
    
    # 1. Validation: deductions equal or exceed gross
    fail_res=c.post('/api/purchases',headers=h,json={
        'branch_id':1,'farmer_id':fid,'idem_key':uuid.uuid4().hex,
        'lines':[{
            'variety':'Java',
            'bag_count':100,
            'bag_tare_kg':'1.000',
            'gross_kg':'100',  # 100 bags * 1kg = 100kg deduction == 100kg gross
            'kapat_kg':'0',
            'rate_per_20kg':'2000'
        }]
    })
    assert fail_res.status_code==422
    assert 'cannot equal or exceed gross' in fail_res.json()['detail']
    
    # 2. Valid multi-line bag tare calculation
    res=c.post('/api/purchases',headers=h,json={
        'branch_id':1,'farmer_id':fid,'idem_key':uuid.uuid4().hex,
        'rst_number':'RST-BAG-01','vehicle_number':'GJ-09-BAGS',
        'lines':[
            {
                'variety':'Java',
                'bag_count':50,
                'bag_tare_kg':'1.000',
                'gross_kg':'1000.000',
                'kapat_kg':'10.000',
                'rate_per_20kg':'2000.00'
            },
            {
                'variety':'Bold',
                'bag_count':30,
                'bag_tare_kg':'1.200',
                'gross_kg':'600.000',
                'kapat_kg':'0.000',
                'rate_per_20kg':'1500.00'
            }
        ]
    })
    assert res.status_code==201, res.text
    p=res.json()['purchase']
    
    # Verification of totals
    assert p['total_bags']==80
    assert p['gross_kg']=='1600.000'
    assert p['kapat_kg']=='96.000'   # (50*1 + 10) + (30*1.2 + 0) = 60 + 36 = 96
    assert p['net_kg']=='1504.000'   # 1600 - 96 = 1504
    assert p['gross_value']=='136300.00'  # 940*100 + 564*75 = 94000 + 42300 = 136300
    assert p['payable']=='136300.00'
    
    # Verification of detail lines
    lines=p['lines']
    assert len(lines)==2
    assert lines[0]['bag_count']==50
    assert lines[0]['bag_tare_kg']=='1.000'
    assert lines[0]['net_kg']=='940.000'
    assert lines[0]['amount']=='94000.00'
    
    assert lines[1]['bag_count']==30
    assert lines[1]['bag_tare_kg']=='1.200'
    assert lines[1]['net_kg']=='564.000'
    assert lines[1]['amount']=='42300.00'
    
    # Verify in list API
    purchases_list=c.get(f"/api/purchases?search={p['number']}").json()
    assert len(purchases_list)==1
    assert purchases_list[0]['total_bags']==80

def test_farmer_khata_ledger_and_fifo_payment(setup):
    c=setup
    h=auth(c,'owner')
    fid=c.post('/api/farmers',headers=h,json={'name':'Govindbhai Patel','village':'Idar','mobile':'9825123456'}).json()['id']
    
    # Bill 1: 50 bags, net 1000 kg, payable ₹100,000 (1000kg * 2000/20)
    b1=c.post('/api/purchases',headers=h,json={
        'branch_id':1,'farmer_id':fid,'idem_key':uuid.uuid4().hex,
        'lines':[{'variety':'Java','bag_count':50,'bag_tare_kg':'0','gross_kg':'1000','kapat_kg':'0','rate_per_20kg':'2000'}]
    }).json()['purchase']
    
    # Bill 2: 30 bags, net 600 kg, payable ₹60,000 (600kg * 2000/20)
    b2=c.post('/api/purchases',headers=h,json={
        'branch_id':2,'farmer_id':fid,'idem_key':uuid.uuid4().hex,
        'lines':[{'variety':'Bold','bag_count':30,'bag_tare_kg':'0','gross_kg':'600','kapat_kg':'0','rate_per_20kg':'2000'}]
    }).json()['purchase']
    
    # 1. Fetch initial Ledger
    ledger=c.get(f'/api/farmers/{fid}/ledger').json()
    assert ledger['farmer']['name']=='Govindbhai Patel'
    s=ledger['summary']
    assert s['total_bills']==2
    assert s['total_bags']==80
    assert s['total_billed']=='160000.00'
    assert s['outstanding_balance']=='160000.00'
    assert s['unallocated_balance']=='160000.00'
    assert len(ledger['entries'])==2
    assert ledger['entries'][0]['credit']=='100000.00'
    assert ledger['entries'][0]['running_balance']=='100000.00'
    assert ledger['entries'][1]['credit']=='60000.00'
    assert ledger['entries'][1]['running_balance']=='160000.00'
    assert ledger['closing_balance']=='160000.00'
    
    # 2. Overpayment validation (> 160000)
    overpay=c.post(f'/api/farmers/{fid}/payments',headers=h,json={
        'idem_key':uuid.uuid4().hex,'method':'CASH','amount':'160001'
    })
    assert overpay.status_code==422
    assert 'exceeds total unallocated' in overpay.json()['detail']
    
    # 3. FIFO lump-sum payment of ₹120,000
    # Expected: clears Bill 1 (₹100,000) and allocates ₹20,000 to Bill 2
    pay_res=c.post(f'/api/farmers/{fid}/payments',headers=h,json={
        'idem_key':uuid.uuid4().hex,'method':'CASH','amount':'120000','reference':'Cash payment batch 1'
    })
    assert pay_res.status_code==201, pay_res.text
    alloc=pay_res.json()['allocations']
    assert len(alloc)==2
    assert alloc[0]['bill']==b1['number']
    assert alloc[0]['amount']=='100000.00'
    assert alloc[1]['bill']==b2['number']
    assert alloc[1]['amount']=='20000.00'
    
    # 4. Check updated Ledger
    ledger_after=c.get(f'/api/farmers/{fid}/ledger').json()
    s2=ledger_after['summary']
    assert s2['total_cleared_payments']=='120000.00'
    assert s2['outstanding_balance']=='40000.00'
    assert s2['unallocated_balance']=='40000.00'
    assert ledger_after['closing_balance']=='40000.00'
    assert len(ledger_after['entries'])==4
    
    # 5. Check individual bill outstanding balances
    detail1=c.get(f"/api/purchases/{b1['id']}").json()
    assert detail1['payments_summary']['outstanding']=='0.00'
    assert detail1['payments_summary']['unallocated']=='0.00'
    
    detail2=c.get(f"/api/purchases/{b2['id']}").json()
    assert detail2['payments_summary']['outstanding']=='40000.00'
    assert detail2['payments_summary']['unallocated']=='40000.00'

def test_point1_point2_direct_farmer_and_dual_payment_settlement(setup):
    """Point 1 & Point 2: Direct farmer entry (create-on-the-fly) and dual payment settlement (Cash + Cheque)."""
    c = setup
    h = auth(c, 'hmtbuy')
    
    # 1. Post a bill with direct inline farmer details (not pre-existing) + Cash & Cheque split
    idem = uuid.uuid4().hex
    res = c.post('/api/purchases', headers=h, json={
        'idem_key': idem,
        'branch_id': 1,
        'farmer_name': 'Rameshbhai Patel',
        'farmer_village': 'Bhiloda',
        'farmer_mobile': '9876543210',
        'rst_number': 'RST-9999',
        'vehicle_number': 'GJ-09-AB-1234',
        'weighbridge_charges': '100.00',
        'other_deductions': '0.00',
        'round_adjustment': '0.00',
        'notes': 'Point 1 & 2 integration test',
        'lines': [{
            'variety': 'Java',
            'bag_count': 50,
            'bag_tare_kg': '1.000',
            'gross_kg': '2050.000', # 2050 - 50 = 2000kg net (100 mann)
            'kapat_kg': '0.000',
            'rate_per_20kg': '2000.00' # 100 * 2000 = 200,000 gross value. Payable = 200,000 - 100 = 199,900
        }],
        'cash_paid': '9900.00',
        'pay_later_cash': '0.00',
        'cheque_number': 'CHQ-88888',
        'cheque_date': '2026-10-29',
        'cheque_amount': '190000.00' # 9900 + 190000 = 199900 (fully settled)
    })
    assert res.status_code == 201, res.text
    bill = res.json()['purchase']
    assert bill['payable'] == '199900.00'
    assert bill['farmer'] == 'Rameshbhai Patel'
    assert bill['village'] == 'Bhiloda'
    assert bill['mobile'] == '9876543210'
    assert bill['cash_paid'] == '9900.00'
    assert bill['cheque_number'] == 'CHQ-88888'
    assert bill['cheque_amount'] == '190000.00'
    
    # Check that payments were auto-created: Cash (CLEARED) and Cheque (PENDING)
    detail = c.get(f"/api/purchases/{bill['id']}", headers=h).json()
    payments = detail['payments']
    assert len(payments) == 2
    cash_pay = next(p for p in payments if p['method'] == 'CASH')
    assert cash_pay['amount'] == '9900.00'
    assert cash_pay['status'] == 'CLEARED'
    
    chq_pay = next(p for p in payments if p['method'] == 'CHEQUE')
    assert chq_pay['amount'] == '190000.00'
    assert chq_pay['status'] == 'PENDING'
    assert chq_pay['reference'] == 'CHQ-88888'
    assert chq_pay['instrument_date'] == '2026-10-29'
    
    # 2. Check that the farmer was automatically created in the database
    farmer_res = c.get('/api/farmers?search=Rameshbhai', headers=h).json()
    assert len(farmer_res) >= 1
    found = next(f for f in farmer_res if f['name'] == 'Rameshbhai Patel' and f['village'] == 'Bhiloda')
    assert found['mobile'] == '9876543210'
    
    # 3. Post a 2nd bill with the SAME farmer name and village (should link to existing farmer, not duplicate)
    idem2 = uuid.uuid4().hex
    res2 = c.post('/api/purchases', headers=h, json={
        'idem_key': idem2,
        'branch_id': 1,
        'farmer_name': 'Rameshbhai Patel',
        'farmer_village': 'Bhiloda',
        'rst_number': 'RST-10000',
        'lines': [{
            'variety': 'Java',
            'bag_count': 10,
            'bag_tare_kg': '1.000',
            'gross_kg': '410.000',
            'rate_per_20kg': '2000.00'
        }]
    })
    assert res2.status_code == 201, res2.text
    bill2 = res2.json()['purchase']
    assert bill2['farmer_id'] == found['id'] # Reused same farmer

def test_point3_market_transport_and_godown_unloading(setup):
    """Point 3: Market transport cost deduction and unload at godown flag."""
    c = setup
    h = auth(c, 'hmtbuy')
    fid = farmer(c, h)
    
    # Bill with Market transport cost ₹350 and Unload at Godown = True
    # Gross: 1000kg at 2000/20kg = ₹100,000
    # Weighbridge: ₹50, Market Transport: ₹350
    # Payable = 100,000 - 50 - 350 = ₹99,600
    res = c.post('/api/purchases', headers=h, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'rst_number': 'RST-TRAN-01',
        'weighbridge_charges': '50.00',
        'market_transport_cost': '350.00',
        'unload_at_godown': True,
        'other_deductions': '0.00',
        'round_adjustment': '0.00',
        'lines': [{
            'variety': 'Bold',
            'bag_count': 0,
            'bag_tare_kg': '0.000',
            'gross_kg': '1000.000',
            'kapat_kg': '0.000',
            'rate_per_20kg': '2000.00'
        }]
    })
    assert res.status_code == 201, res.text
    p = res.json()['purchase']
    assert p['payable'] == '99600.00'
    assert p['market_transport_cost'] == '350.00'
    assert p['unload_at_godown'] is True
    
    # Check detail endpoint returns both fields
    detail = c.get(f"/api/purchases/{p['id']}", headers=h).json()
    assert detail['market_transport_cost'] == '350.00'
    assert detail['unload_at_godown'] is True

def test_point4_bill_date_picker_and_next_sequence_preview(setup):
    """Point 4: Bill date picker and next sequence number preview endpoint."""
    c = setup
    h = auth(c, 'hmtbuy')
    fid = farmer(c, h)

    # 1. Check next sequence number endpoint for Branch 1
    next_res = c.get('/api/purchases/next-number?branch_id=1', headers=h)
    assert next_res.status_code == 200, next_res.text
    seq = next_res.json()
    assert 'HMT/' in seq['formatted']
    assert seq['branch_code'] == 'HMT'
    expected_num = seq['next_number']

    # 2. Post a bill with custom back-dated purchase_date (e.g. 2026-10-15)
    custom_date = '2026-10-15'
    res = c.post('/api/purchases', headers=h, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'purchase_date': custom_date,
        'rst_number': 'RST-DATE-01',
        'lines': [{
            'variety': 'Java',
            'bag_count': 0,
            'bag_tare_kg': '0.000',
            'gross_kg': '500.000',
            'rate_per_20kg': '2000.00'
        }]
    })
    assert res.status_code == 201, res.text
    p = res.json()['purchase']
    assert p['date'] == custom_date
    assert f'{expected_num:06d}' in p['number']

    # 3. Next sequence number should now be incremented
    next_res_after = c.get('/api/purchases/next-number?branch_id=1', headers=h).json()
    assert next_res_after['next_number'] == expected_num + 1

def test_point7_batch_payment_status_update(setup):
    """Point 7: Batch payment status update for month-wise inline clearing register."""
    c = setup
    # 1. Login as buyer to create farmer and bills
    h_buy = auth(c, 'hmtbuy')
    fid = farmer(c, h_buy)

    res1 = c.post('/api/purchases', headers=h_buy, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'lines': [{'variety': 'Java', 'bag_count': 0, 'gross_kg': '100.000', 'rate_per_20kg': '2000.00'}], # 10,000
        'cheque_number': 'BATCH-001',
        'cheque_date': '2026-10-25',
        'cheque_amount': '10000.00'
    })
    b1 = res1.json()['purchase']

    res2 = c.post('/api/purchases', headers=h_buy, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'lines': [{'variety': 'Java', 'bag_count': 0, 'gross_kg': '200.000', 'rate_per_20kg': '2000.00'}], # 20,000
        'cheque_number': 'BATCH-002',
        'cheque_date': '2026-10-26',
        'cheque_amount': '20000.00'
    })
    b2 = res2.json()['purchase']

    p1 = c.get(f"/api/purchases/{b1['id']}", headers=h_buy).json()['payments'][0]
    p2 = c.get(f"/api/purchases/{b2['id']}", headers=h_buy).json()['payments'][0]
    assert p1['status'] == 'PENDING'
    assert p2['status'] == 'PENDING'

    # 2. Login as accountant to perform batch clearance update
    h_acct = auth(c, 'hmtacct')
    batch_res = c.post('/api/payments/batch-status', headers=h_acct, json={
        'items': [
            {'payment_id': p1['id'], 'status': 'CLEARED', 'clearance_date': '2026-10-28'},
            {'payment_id': p2['id'], 'status': 'BOUNCED', 'clearance_date': None}
        ]
    })
    assert batch_res.status_code == 200, batch_res.text
    data = batch_res.json()
    assert data['updated_count'] == 2

    # 3. Verify updated statuses in payments endpoint with month filtering
    month_res = c.get('/api/payments?branch_id=1&month=2026-10', headers=h_acct).json()
    found_p1 = next(p for p in month_res if p['id'] == p1['id'])
    found_p2 = next(p for p in month_res if p['id'] == p2['id'])
    assert found_p1['status'] == 'CLEARED'
    assert found_p1['instrument_date'] == '2026-10-28'
    assert found_p2['status'] == 'BOUNCED'








def test_feature3_edit_purchase_bill(setup):
    c = setup
    h_buy = auth(c, 'hmtbuy')
    fid = farmer(c, h_buy)

    # 1. Create a bill
    res = c.post('/api/purchases', headers=h_buy, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'rst_number': 'RST-INITIAL',
        'lines': [{'variety': 'Java', 'bag_count': 10, 'bag_tare_kg': '1.000', 'gross_kg': '510.000', 'kapat_kg': '0.000', 'rate_per_20kg': '2000.00'}],
        'weighbridge_charges': '20.00',
        'market_transport_cost': '0.00',
        'round_adjustment': '0.00',
        'cash_paid': '10000.00',
        'cheque_number': 'CHQ-ORIG',
        'cheque_date': '2026-10-27',
        'cheque_amount': '39980.00'
    })
    assert res.status_code == 201
    b = res.json()['purchase']
    bill_id = b['id']
    assert b['payable'] == '49980.00'
    assert b['cash_paid'] == '10000.00'
    assert b['cheque_amount'] == '39980.00'

    # 2. Operator amends the bill ("સુધારો")
    edit_res = c.put(f'/api/purchases/{bill_id}', headers=h_buy, json={
        'farmer_id': fid,
        'rst_number': 'RST-AMENDED-99',
        'vehicle_number': 'GJ-09-AB-1234',
        'lines': [{'variety': 'Bold', 'bag_count': 20, 'bag_tare_kg': '1.000', 'gross_kg': '1020.000', 'kapat_kg': '0.000', 'rate_per_20kg': '2200.00'}],
        'weighbridge_charges': '20.00',
        'market_transport_cost': '100.00',
        'unload_at_godown': True,
        'round_adjustment': '0.00',
        'cash_paid': '20000.00',
        'pay_later_cash': '10000.00',
        'pay_later_date': '2026-11-05',
        'cheque_number': 'CHQ-AMENDED-01',
        'cheque_date': '2026-10-29',
        'cheque_amount': '79880.00'
    })
    assert edit_res.status_code == 200, edit_res.text
    edited = edit_res.json()['purchase']
    assert edited['rst'] == 'RST-AMENDED-99'
    assert edited['vehicle'] == 'GJ-09-AB-1234'
    assert edited['total_bags'] == 20
    assert edited['net_kg'] == '1000.000'
    assert edited['payable'] == '109880.00'
    assert edited['market_transport_cost'] == '100.00'
    assert edited['unload_at_godown'] is True
    assert edited['cash_paid'] == '20000.00'
    assert edited['pay_later_cash'] == '10000.00'
    assert edited['cheque_number'] == 'CHQ-AMENDED-01'
    assert edited['cheque_amount'] == '79880.00'

    # Check payment records are synchronized
    detail = c.get(f'/api/purchases/{bill_id}', headers=h_buy).json()
    payments = detail['payments']
    cash_p = next(p for p in payments if p['method'] == 'CASH')
    cheq_p = next(p for p in payments if p['method'] == 'CHEQUE')
    assert cash_p['amount'] == '20000.00'
    assert cheq_p['amount'] == '79880.00'
    assert cheq_p['reference'] == 'CHQ-AMENDED-01'

    # 3. Create another bill without cash, void it, and verify cannot edit a voided bill
    res_voidable = c.post('/api/purchases', headers=h_buy, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'lines': [{'variety': 'Java', 'bag_count': 5, 'bag_tare_kg': '1.000', 'gross_kg': '205.000', 'kapat_kg': '0.000', 'rate_per_20kg': '2000.00'}]
    })
    voidable_id = res_voidable.json()['purchase']['id']
    c.post(f'/api/purchases/{voidable_id}/void', headers=h_buy, json={'reason': 'Incorrect vehicle ticket entered'})

    attempt_edit_void = c.put(f'/api/purchases/{voidable_id}', headers=h_buy, json={
        'farmer_id': fid,
        'lines': [{'variety': 'Java', 'bag_count': 5, 'bag_tare_kg': '1.000', 'gross_kg': '205.000', 'kapat_kg': '0.000', 'rate_per_20kg': '2000.00'}]
    })
    assert attempt_edit_void.status_code == 400
    assert 'voided' in attempt_edit_void.text.lower()


def test_pending_cheques_count_endpoint(setup):
    c = setup
    h_buy = auth(c, 'hmtbuy')
    fid = farmer(c, h_buy)

    # 1. Check initial pending count
    init_cnt = c.get('/api/payments/pending-count?branch_id=1', headers=h_buy).json()['pending_count']

    # 2. Create bill with pending cheque
    c.post('/api/purchases', headers=h_buy, json={
        'idem_key': uuid.uuid4().hex,
        'branch_id': 1,
        'farmer_id': fid,
        'lines': [{'variety': 'Java', 'bag_count': 10, 'bag_tare_kg': '1.000', 'gross_kg': '510.000', 'kapat_kg': '0.000', 'rate_per_20kg': '2000.00'}],
        'cheque_number': 'BADGE-CHQ-1',
        'cheque_date': '2026-10-27',
        'cheque_amount': '15000.00'
    })

    # 3. Verify count incremented
    new_cnt = c.get('/api/payments/pending-count?branch_id=1', headers=h_buy).json()['pending_count']
    assert new_cnt == init_cnt + 1
