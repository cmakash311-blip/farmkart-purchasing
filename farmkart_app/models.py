from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, Numeric, Text, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now_utc(): return datetime.now(timezone.utc)

class Branch(Base):
    __tablename__ = 'branches'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(100))

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # OWNER, PURCHASE, ACCOUNTS, VIEWER
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    branch: Mapped['Branch | None'] = relationship()

class SessionToken(Base):
    __tablename__ = 'session_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped['User'] = relationship()

class Farmer(Base):
    __tablename__ = 'farmers'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140))
    village: Mapped[str] = mapped_column(String(140))
    mobile: Mapped[str] = mapped_column(String(20), default='')
    cooperative: Mapped[str] = mapped_column(String(140), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class BillSequence(Base):
    __tablename__ = 'bill_sequences'
    __table_args__ = (UniqueConstraint('branch_id','fy',name='uq_branch_fy'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    fy: Mapped[str] = mapped_column(String(10))
    last_number: Mapped[int] = mapped_column(Integer, default=0)

class Purchase(Base):
    __tablename__ = 'purchases'
    __table_args__ = (Index('idx_purchase_branch_date','branch_id','purchase_date'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(45), unique=True)
    idem_key: Mapped[str] = mapped_column(String(100), unique=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'))
    farmer_id: Mapped[int] = mapped_column(ForeignKey('farmers.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    purchase_date: Mapped[date] = mapped_column(Date)
    rst_number: Mapped[str] = mapped_column(String(80), default='')
    vehicle_number: Mapped[str] = mapped_column(String(60), default='')
    gross_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    kapat_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    net_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    gross_value: Mapped[Decimal] = mapped_column(Numeric(15,2))
    weighbridge_charges: Mapped[Decimal] = mapped_column(Numeric(15,2))
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(15,2))
    round_adjustment: Mapped[Decimal] = mapped_column(Numeric(15,2))
    payable: Mapped[Decimal] = mapped_column(Numeric(15,2))
    notes: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='POSTED')
    total_bags: Mapped[int] = mapped_column(Integer, default=0)
    # Point 1: Payment settlement captured at bill-creation time
    cash_paid: Mapped[Decimal] = mapped_column(Numeric(15,2), default=Decimal('0'))
    pay_later_cash: Mapped[Decimal] = mapped_column(Numeric(15,2), default=Decimal('0'))
    pay_later_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    farmer: Mapped[Farmer] = relationship()
    branch: Mapped[Branch] = relationship()
    lines: Mapped[list['PurchaseLine']] = relationship(back_populates='purchase', cascade='all, delete-orphan', order_by='PurchaseLine.id')
    payments: Mapped[list['Payment']] = relationship(back_populates='purchase', order_by='Payment.id')

class PurchaseLine(Base):
    __tablename__ = 'purchase_lines'
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('purchases.id'))
    variety: Mapped[str] = mapped_column(String(80))
    bag_count: Mapped[int] = mapped_column(Integer, default=0)
    bag_tare_kg: Mapped[Decimal] = mapped_column(Numeric(15,3), default=Decimal('0'))
    gross_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    kapat_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    net_kg: Mapped[Decimal] = mapped_column(Numeric(15,3))
    rate_per_20kg: Mapped[Decimal] = mapped_column(Numeric(15,2))
    line_amount: Mapped[Decimal] = mapped_column(Numeric(15,2))
    purchase: Mapped[Purchase] = relationship(back_populates='lines')

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    idem_key: Mapped[str] = mapped_column(String(100), unique=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('purchases.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    method: Mapped[str] = mapped_column(String(12))  # CASH, CHEQUE, BANK
    status: Mapped[str] = mapped_column(String(12))  # PENDING, CLEARED, BOUNCED
    amount: Mapped[Decimal] = mapped_column(Numeric(15,2))
    reference: Mapped[str] = mapped_column(String(100), default='')
    instrument_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    purchase: Mapped[Purchase] = relationship(back_populates='payments')

class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
