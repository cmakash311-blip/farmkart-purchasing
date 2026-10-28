"""Run: python -m farmkart_app.bootstrap init ; python -m farmkart_app.bootstrap user"""
import argparse, getpass
from sqlalchemy import select
from .db import Base, engine, SessionLocal
from .models import Branch, User
from .security import encode_password

def initialize():
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        for code,name in [('HMT','Himatnagar'),('MDS','Modasa')]:
            if not db.scalar(select(Branch).where(Branch.code==code)):
                db.add(Branch(code=code,name=name))
    print('Database schema initialized. Factories: HMT (Himatnagar), MDS (Modasa).')

def create_user(username=None, name=None, role=None, branch_id=None, password=None):
    with SessionLocal.begin() as db:
        print('Existing factories:', [(x.id,x.name) for x in db.scalars(select(Branch))])
        username = (username or input('Username: ')).strip().lower()
        name = (name or input('Full name: ')).strip()
        role = (role or input('Role (OWNER / PURCHASE / ACCOUNTS / VIEWER): ')).strip().upper()
        if role not in ['OWNER','PURCHASE','ACCOUNTS','VIEWER']: raise ValueError('Invalid role')
        if branch_id is None and role != 'OWNER':
            branch_id = int(input('Branch ID (from above): '))
        if branch_id is not None and not db.get(Branch,branch_id): raise ValueError('Unknown factory')
        if db.scalar(select(User).where(User.username==username)): raise ValueError('Username already exists')
        if password is None:
            pwd=getpass.getpass('Password (12+ chars): ')
            again=getpass.getpass('Confirm password: ')
            if pwd != again: raise ValueError('Passwords do not match')
        else:
            pwd = password
        db.add(User(username=username,full_name=name,password_hash=encode_password(pwd),role=role,branch_id=branch_id))
    print('Account created for',username)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['init','user'])
    p.add_argument('--username', default=None)
    p.add_argument('--name', default=None)
    p.add_argument('--role', default=None)
    p.add_argument('--branch-id', type=int, default=None)
    p.add_argument('--password', default=None)
    args=p.parse_args()
    if args.action=='init':
        initialize()
    else:
        create_user(username=args.username, name=args.name, role=args.role, branch_id=args.branch_id, password=args.password)
