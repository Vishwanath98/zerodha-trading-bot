from typing import Optional, Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.models import Signal, ResearchCall, AuditLog
from src.services.signal_parser import parser
from src.services.filter_engine import filter_engine
from src.services.risk_engine import risk_engine
from src.services.position_manager import PositionManager
from src.services.executor import executor
from src.core.logger import logger


class SignalProcessor:
    """
    Main signal processing pipeline:
    1. Parse signal
    2. Validate with filters
    3. Check risk
    4. Execute trade
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_signal(self, source: str, raw_message: str) -> Dict:
        """Process a raw signal through the pipeline."""
        
        signal = Signal(
            source=source,
            raw_message=raw_message,
            status='pending'
        )
        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)
        
        logger.info(f"Processing signal {signal.id}: {raw_message[:50]}...")
        
        parsed = parser.parse(raw_message)
        
        if not parsed:
            signal.status = 'rejected'
            signal.error_message = 'Failed to parse signal'
            await self.db.commit()
            return {'success': False, 'error': 'Parse failed', 'signal_id': signal.id}
        
        signal.parsed_signal = {
            'underlying': parsed.underlying,
            'strike': parsed.strike,
            'option_type': parsed.option_type,
            'action': parsed.action,
            'entry_price': parsed.entry_price,
            'stop_loss': parsed.stop_loss,
            'target': parsed.target,
            'quantity': parsed.quantity,
            'expiry': parsed.expiry
        }
        signal.confidence = parsed.confidence
        await self.db.commit()
        
        filter_results = await self._run_filters(parsed)
        
        risk_results = await self._run_risk_checks(parsed)
        
        can_execute = all([
            parsed.confidence >= 0.5,
            risk_engine.get_passed_checks(risk_results)
        ])
        
        if can_execute:
            signal.status = 'validated'
            await self.db.commit()
            
            execution_result = await self._execute_trade(parsed, signal.id)
            
            if execution_result['success']:
                signal.status = 'executed'
            else:
                signal.status = 'rejected'
                signal.error_message = execution_result.get('error')
            
            await self.db.commit()
            return execution_result
        else:
            signal.status = 'rejected'
            signal.error_message = 'Failed risk/filter checks'
            await self.db.commit()
            
            return {
                'success': False,
                'signal_id': signal.id,
                'filter_results': filter_results,
                'risk_results': {k: {'passed': v.passed, 'message': v.message} 
                               for k, v in risk_results.items()}
            }
    
    async def _run_filters(self, parsed) -> Dict:
        """Run technical analysis filters."""
        direction = 'long' if parsed.action == 'BUY' else 'short'
        
        candles = []
        vix = 15.0
        
        return filter_engine.run_all_filters(candles, vix, direction)
    
    async def _run_risk_checks(self, parsed) -> Dict:
        """Run risk engine checks."""
        market_data = {'ltp': parsed.entry_price}
        
        signal_data = {
            'entry_price': parsed.entry_price,
            'stop_loss': parsed.stop_loss,
            'target': parsed.target,
            'option_type': parsed.option_type,
            'created_at': datetime.utcnow()
        }
        
        position_manager = PositionManager(self.db)
        open_positions = await position_manager.get_open_positions()
        daily_pnl = await position_manager.get_daily_pnl()
        
        return risk_engine.run_all_checks(
            signal_data, market_data, len(open_positions), daily_pnl
        )
    
    async def _execute_trade(self, parsed, signal_id: int) -> Dict:
        """Execute the trade via Zerodha."""
        
        symbol = parser.generate_symbol(
            parsed.underlying,
            parsed.strike,
            parsed.option_type,
            parsed.expiry
        )
        
        quantity = parsed.quantity or risk_engine.calculate_position_size(
            parsed.entry_price or 0,
            parsed.stop_loss or 0
        )
        
        transaction_type = 'BUY' if parsed.action == 'BUY' else 'SELL'
        
        entry_price = parsed.entry_price
        
        if not entry_price:
            quote = executor.get_quote(symbol)
            if quote:
                entry_price = quote.get('last_price')
        
        order_result = executor.place_market_order(
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity
        )
        
        if order_result.success:
            position_manager = PositionManager(self.db)
            position = await position_manager.open_position(
                signal_data={},
                instrument_token=symbol,
                symbol=symbol,
                quantity=quantity if transaction_type == 'BUY' else -quantity,
                entry_price=entry_price or 0,
                stop_loss=parsed.stop_loss,
                target=parsed.target,
                signal_id=signal_id
            )
            
            await self._log_action('trade_executed', {
                'signal_id': signal_id,
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': entry_price,
                'order_id': order_result.order_id
            })
            
            return {
                'success': True,
                'signal_id': signal_id,
                'position_id': position.id,
                'order_id': order_result.order_id,
                'symbol': symbol,
                'entry_price': entry_price
            }
        
        return {
            'success': False,
            'signal_id': signal_id,
            'error': order_result.message
        }
    
    async def _log_action(self, action: str, details: dict):
        """Log action to audit."""
        log = AuditLog(action=action, details=details)
        self.db.add(log)
        await self.db.commit()


class ResearchValidator:
    """
    Validate research/calls from external agents.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def validate_research(self, research_id: int) -> Dict:
        """Validate research against filters and return confidence."""
        
        result = await self.db.execute(
            select(ResearchCall).where(ResearchCall.id == research_id)
        )
        research = result.scalar_one_or_none()
        
        if not research:
            return {'error': 'Research not found'}
        
        content = research.content
        
        parsed = parser.parse(content)
        
        if not parsed:
            research.validated = False
            research.validation_result = {'error': 'Parse failed'}
            await self.db.commit()
            return {'validated': False}
        
        direction = 'long' if parsed.action == 'BUY' else 'short'
        filter_results = await self._run_filters(parsed)
        
        confidence = parsed.confidence * 0.5
        filter_conf = filter_engine.calculate_overall_confidence(filter_results)
        confidence = confidence * 0.3 + filter_conf * 0.5
        
        research.validated = confidence >= 0.5
        research.confidence = confidence
        research.parsed_data = {
            'underlying': parsed.underlying,
            'strike': parsed.strike,
            'option_type': parsed.option_type,
            'action': parsed.action
        }
        research.validation_result = {
            'passed': research.validated,
            'confidence': confidence,
            'filter_results': {k: {'passed': r.passed, 'confidence': r.confidence} 
                             for k, r in filter_results.items()}
        }
        
        await self.db.commit()
        
        return {
            'validated': research.validated,
            'confidence': confidence,
            'parsed': research.parsed_data,
            'filter_results': filter_results
        }
    
    async def _run_filters(self, parsed):
        """Run filters for research."""
        direction = 'long' if parsed.action == 'BUY' else 'short'
        candles = []
        vix = 15.0
        return filter_engine.run_all_filters(candles, vix, direction)
