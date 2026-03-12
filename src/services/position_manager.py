from typing import Optional, List, Dict
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.models import Position, Order, AuditLog
from src.services.executor import executor
from src.core.logger import logger


class PositionManager:
    """
    Manages trading positions, monitors P&L, handles exits.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def open_position(self, signal_data: dict, instrument_token: str,
                           symbol: str, quantity: int, entry_price: float,
                           stop_loss: Optional[float] = None,
                           target: Optional[float] = None,
                           signal_id: Optional[int] = None) -> Position:
        """Open a new position."""
        
        position = Position(
            signal_id=signal_id,
            instrument_token=instrument_token,
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            status='open'
        )
        
        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)
        
        await self._log_action('position_opened', {
            'position_id': position.id,
            'symbol': symbol,
            'quantity': quantity,
            'entry_price': entry_price
        })
        
        logger.info(f"Position opened: {symbol} qty={quantity} @ {entry_price}")
        
        return position
    
    async def close_position(self, position_id: int, exit_price: float,
                            reason: str = 'manual') -> Optional[Position]:
        """Close an existing position."""
        
        result = await self.db.execute(
            select(Position).where(Position.id == position_id)
        )
        position = result.scalar_one_or_none()
        
        if not position:
            return None
        
        position.status = 'closed'
        position.current_price = exit_price
        position.pnl = (exit_price - position.entry_price) * position.quantity
        position.closed_at = datetime.utcnow()
        
        await self.db.commit()
        
        await self._log_action('position_closed', {
            'position_id': position_id,
            'exit_price': exit_price,
            'pnl': position.pnl,
            'reason': reason
        })
        
        logger.info(f"Position closed: {position.symbol} @ {exit_price}, PnL: {position.pnl}")
        
        return position
    
    async def update_position_prices(self) -> List[Position]:
        """Update current prices for all open positions."""
        
        result = await self.db.execute(
            select(Position).where(Position.status == 'open')
        )
        positions = result.scalars().all()
        
        for pos in positions:
            try:
                quote = executor.get_quote(pos.symbol)
                if quote:
                    pos.current_price = quote.get('last_price', pos.entry_price)
                    pos.pnl = (pos.current_price - pos.entry_price) * pos.quantity
            except Exception as e:
                logger.error(f"Error updating price for {pos.symbol}: {e}")
        
        await self.db.commit()
        return positions
    
    async def check_stop_loss(self, position_id: int) -> bool:
        """Check if position hit stop loss."""
        
        result = await self.db.execute(
            select(Position).where(Position.id == position_id)
        )
        position = result.scalar_one_or_none()
        
        if not position or not position.stop_loss:
            return False
        
        current_price = position.current_price
        direction = 'long'
        
        if direction == 'long':
            if current_price <= position.stop_loss:
                return True
        else:
            if current_price >= position.stop_loss:
                return True
        
        return False
    
    async def check_target(self, position_id: int) -> bool:
        """Check if position hit target."""
        
        result = await self.db.execute(
            select(Position).where(Position.id == position_id)
        )
        position = result.scalar_one_or_none()
        
        if not position or not position.target:
            return False
        
        current_price = position.current_price
        
        if current_price >= position.target:
            return True
        
        return False
    
    async def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        result = await self.db.execute(
            select(Position).where(Position.status == 'open')
        )
        return result.scalars().all()
    
    async def get_position(self, position_id: int) -> Optional[Position]:
        """Get position by ID."""
        result = await self.db.execute(
            select(Position).where(Position.id == position_id)
        )
        return result.scalar_one_or_none()
    
    async def get_daily_pnl(self) -> float:
        """Calculate today's P&L."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = await self.db.execute(
            select(Position).where(
                Position.status == 'closed',
                Position.closed_at >= today_start
            )
        )
        positions = result.scalars().all()
        
        return sum(p.pnl for p in positions)
    
    async def get_total_pnl(self) -> float:
        """Get total P&L across all positions."""
        result = await self.db.execute(
            select(Position).where(Position.status == 'closed')
        )
        positions = result.scalars().all()
        
        return sum(p.pnl for p in positions)
    
    async def square_off_all(self, reason: str = 'end_of_day') -> List[dict]:
        """Square off all open positions."""
        
        positions = await self.get_open_positions()
        closed = []
        
        for pos in positions:
            try:
                quote = executor.get_quote(pos.symbol)
                exit_price = quote.get('last_price') if quote else pos.entry_price
                
                order_result = executor.place_market_order(
                    symbol=pos.symbol,
                    transaction_type='SELL' if pos.quantity > 0 else 'BUY',
                    quantity=abs(pos.quantity)
                )
                
                if order_result.success:
                    await self.close_position(pos.id, exit_price, reason)
                    closed.append({
                        'position_id': pos.id,
                        'symbol': pos.symbol,
                        'exit_price': exit_price
                    })
            except Exception as e:
                logger.error(f"Error squaring off {pos.symbol}: {e}")
        
        return closed
    
    async def _log_action(self, action: str, details: dict):
        """Log action to audit table."""
        log = AuditLog(action=action, details=details)
        self.db.add(log)
        await self.db.commit()


class PositionMonitor:
    """
    Background monitor for positions - checks SL, target, etc.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.manager = PositionManager(db)
    
    async def run_checks(self) -> Dict:
        """Run all position checks."""
        results = {
            'sl_hit': [],
            'target_hit': [],
            'updated': []
        }
        
        positions = await self.manager.get_open_positions()
        
        for pos in positions:
            try:
                quote = executor.get_quote(pos.symbol)
                if not quote:
                    continue
                
                pos.current_price = quote.get('last_price', pos.entry_price)
                pos.pnl = (pos.current_price - pos.entry_price) * pos.quantity
                
                if await self.manager.check_stop_loss(pos.id):
                    logger.info(f"SL hit for {pos.symbol}")
                    results['sl_hit'].append(pos.id)
                    
                    order_result = executor.place_market_order(
                        symbol=pos.symbol,
                        transaction_type='SELL',
                        quantity=abs(pos.quantity)
                    )
                    
                    if order_result.success:
                        await self.manager.close_position(
                            pos.id, pos.current_price, 'stop_loss'
                        )
                
                elif await self.manager.check_target(pos.id):
                    logger.info(f"Target hit for {pos.symbol}")
                    results['target_hit'].append(pos.id)
                    
                    order_result = executor.place_market_order(
                        symbol=pos.symbol,
                        transaction_type='SELL',
                        quantity=abs(pos.quantity)
                    )
                    
                    if order_result.success:
                        await self.manager.close_position(
                            pos.id, pos.current_price, 'target'
                        )
                
                results['updated'].append(pos.id)
                
            except Exception as e:
                logger.error(f"Error checking position {pos.id}: {e}")
        
        await self.db.commit()
        return results
