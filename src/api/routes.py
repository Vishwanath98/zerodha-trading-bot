from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timedelta

from src.models.models import Signal, Position, Order, AuditLog, ResearchCall
from src.models.models import get_db
from src.services.position_manager import PositionManager
from src.services.signal_processor import SignalProcessor, ResearchValidator
from src.adapters.csv_adapter import csv_adapter
from src.core.logger import logger

router = APIRouter()


class SignalResponse(BaseModel):
    id: int
    source: str
    raw_message: str
    confidence: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class PositionResponse(BaseModel):
    id: int
    symbol: str
    quantity: int
    entry_price: float
    current_price: Optional[float]
    pnl: float
    stop_loss: Optional[float]
    target: Optional[float]
    status: str
    opened_at: datetime
    
    class Config:
        from_attributes = True


class ExitRequest(BaseModel):
    exit_price: float


@router.get("/signals", response_model=List[SignalResponse])
async def list_signals(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List recent signals."""
    query = select(Signal).order_by(Signal.created_at.desc())
    
    if status:
        query = query.where(Signal.status == status)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    """Get signal details."""
    result = await db.execute(
        select(Signal).where(Signal.id == signal_id)
    )
    signal = result.scalar_one_or_none()
    
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    
    return signal


@router.get("/positions", response_model=List[PositionResponse])
async def list_positions(
    status: Optional[str] = 'open',
    db: AsyncSession = Depends(get_db)
):
    """List positions."""
    query = select(Position)
    
    if status:
        query = query.where(Position.status == status)
    
    query = query.order_by(Position.opened_at.desc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/positions/{position_id}")
async def get_position(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get position details."""
    result = await db.execute(
        select(Position).where(Position.id == position_id)
    )
    position = result.scalar_one_or_none()
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    return position


@router.post("/positions/{position_id}/exit")
async def exit_position(
    position_id: int,
    request: ExitRequest,
    db: AsyncSession = Depends(get_db)
):
    """Exit a position manually."""
    manager = PositionManager(db)
    
    position = await manager.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    position = await manager.close_position(position_id, request.exit_price, 'manual')
    
    return {
        'success': True,
        'position_id': position_id,
        'exit_price': request.exit_price,
        'pnl': position.pnl if position else 0
    }


@router.post("/positions/square-off")
async def square_off_all(db: AsyncSession = Depends(get_db)):
    """Square off all positions."""
    manager = PositionManager(db)
    closed = await manager.square_off_all('manual_squareoff')
    
    return {
        'success': True,
        'closed_count': len(closed),
        'positions': closed
    }


@router.get("/orders")
async def list_orders(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List order history."""
    result = await db.execute(
        select(Order).order_by(Order.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100,
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List audit logs."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    
    if action:
        query = query.where(AuditLog.action == action)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/signals/csv")
async def upload_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload CSV with signals."""
    content = await file.read()
    content_str = content.decode('utf-8')
    
    signals = csv_adapter.parse_csv(content_str)
    
    processed = 0
    for signal_data in signals:
        processor = SignalProcessor(db)
        result = await processor.process_signal(
            source='csv',
            raw_message=signal_data['raw_message']
        )
        if result.get('success'):
            processed += 1
    
    return {
        'success': True,
        'total': len(signals),
        'processed': processed
    }


@router.get("/signals/csv-template")
async def get_csv_template():
    """Get CSV template."""
    return {"template": csv_adapter.generate_csv_template()}


@router.get("/research")
async def list_research(
    validated: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List research calls."""
    query = select(ResearchCall).order_by(ResearchCall.created_at.desc())
    
    if validated is not None:
        query = query.where(ResearchCall.validated == validated)
    
    result = await db.execute(query.limit(50))
    return result.scalars().all()


@router.post("/research/{research_id}/validate")
async def validate_research(research_id: int, db: AsyncSession = Depends(get_db)):
    """Validate a research call."""
    validator = ResearchValidator(db)
    result = await validator.validate_research(research_id)
    return result


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get trading statistics."""
    manager = PositionManager(db)
    
    daily_pnl = await manager.get_daily_pnl()
    total_pnl = await manager.get_total_pnl()
    
    open_positions = await manager.get_open_positions()
    
    today = datetime.utcnow().date()
    signals_today = await db.execute(
        select(Signal).where(
            Signal.created_at >= today
        )
    )
    signals = signals_today.scalars().all()
    
    executed = sum(1 for s in signals if s.status == 'executed')
    rejected = sum(1 for s in signals if s.status == 'rejected')
    
    return {
        'daily_pnl': daily_pnl,
        'total_pnl': total_pnl,
        'open_positions': len(open_positions),
        'signals_today': len(signals),
        'executed_today': executed,
        'rejected_today': rejected
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }
