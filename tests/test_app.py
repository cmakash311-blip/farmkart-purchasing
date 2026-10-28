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
