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
