import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

URL = os.getenv('DATABASE_URL', 'sqlite:///./farmkart_demo.db')
if URL.startswith('postgres://'):
    URL = URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif URL.startswith('postgresql://') and not URL.startswith('postgresql+'):
    URL = URL.replace('postgresql://', 'postgresql+psycopg://', 1)

CONNECT_ARGS = {'check_same_thread': False} if URL.startswith('sqlite') else {}
engine = create_engine(URL, pool_pre_ping=True, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
