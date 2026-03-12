from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, DeclarativeBase
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, Index
from sqlalchemy.sql import func
from src.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)  # telegram, webhook, csv, research
    raw_message = Column(Text, nullable=False)
    parsed_signal = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.0)
    status = Column(String(20), default="pending")  # pending, validated, executed, rejected
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class Position(Base):
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, nullable=True)
    instrument_token = Column(String(20), nullable=False)
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(10), default="NSE")
    product = Column(String(10), default="MIS")  # MIS, NRML
    quantity = Column(Integer, default=1)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    pnl = Column(Float, default=0.0)
    status = Column(String(20), default="open")  # open, closed, cancelled
    entry_order_id = Column(String(50), nullable=True)
    exit_order_id = Column(String(50), nullable=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, nullable=True)
    order_id = Column(String(50), nullable=True)
    exchange_order_id = Column(String(50), nullable=True)
    instrument_token = Column(String(20), nullable=False)
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(10), default="NSE")
    transaction_type = Column(String(10), nullable=False)  # BUY, SELL
    product = Column(String(10), default="MIS")
    order_type = Column(String(20), default="MARKET")  # MARKET, LIMIT, SL
    quantity = Column(Integer, default=1)
    price = Column(Float, nullable=True)
    trigger_price = Column(Float, nullable=True)
    filled_quantity = Column(Integer, default=0)
    average_price = Column(Float, nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, OPEN, COMPLETED, REJECTED, CANCELLED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    filled_at = Column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ResearchCall(Base):
    __tablename__ = "research_calls"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)  # agent_name, manual
    content = Column(Text, nullable=False)
    parsed_data = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.0)
    validated = Column(Boolean, default=False)
    validation_result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Instrument(Base):
    __tablename__ = "instruments"
    
    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String(20), unique=True, index=True)
    trading_symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(10), default="NSE")
    instrument_type = Column(String(20), nullable=False)  # CE, PE, FUT, EQ
    underlying_symbol = Column(String(20), nullable=True)
    strike_price = Column(Float, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    lot_size = Column(Integer, default=1)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_underlying_expiry', 'underlying_symbol', 'expiry_date'),
    )


class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String(20), nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    ltp = Column(Float, nullable=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)
    oi = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
