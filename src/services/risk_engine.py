from typing import Optional
from dataclasses import dataclass
from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()


@dataclass
class RiskCheckResult:
    passed: bool
    message: str
    suggested_quantity: Optional[int] = None
    adjusted_sl: Optional[float] = None


class RiskEngine:
    """
    Risk management engine for position sizing and risk control.
    """
    
    def __init__(self):
        self.max_daily_loss = settings.max_daily_loss
        self.risk_per_trade = settings.risk_per_trade
        self.max_positions = settings.max_positions
        self.default_quantity = settings.default_quantity
        self.paper_trading = settings.paper_trading
        
        self.daily_pnl = 0.0
        self.positions_today = 0
    
    def calculate_position_size(self, entry_price: float, stop_loss: float,
                                account_balance: float = 100000) -> int:
        """Calculate position size based on risk per trade."""
        if stop_loss and entry_price:
            risk_per_share = abs(entry_price - stop_loss)
            if risk_per_share > 0:
                risk_amount = account_balance * (self.risk_per_trade / 100)
                quantity = int(risk_amount / risk_per_share)
                return max(1, quantity)
        
        return self.default_quantity
    
    def check_max_daily_loss(self, current_pnl: float) -> RiskCheckResult:
        """Check if max daily loss limit reached."""
        if abs(current_pnl) >= self.max_daily_loss:
            return RiskCheckResult(
                passed=False,
                message=f"Max daily loss of {self.max_daily_loss} reached. Current PnL: {current_pnl}"
            )
        return RiskCheckResult(
            passed=True,
            message=f"Daily loss OK. Current PnL: {current_pnl}"
        )
    
    def check_max_positions(self, current_positions: int) -> RiskCheckResult:
        """Check if max positions limit reached."""
        if current_positions >= self.max_positions:
            return RiskCheckResult(
                passed=False,
                message=f"Max positions ({self.max_positions}) reached"
            )
        return RiskCheckResult(
            passed=True,
            message=f"Position slots available. Current: {current_positions}/{self.max_positions}"
        )
    
    def check_spread(self, entry_price: float, ltp: float, 
                    max_spread_pct: float = 1.0) -> RiskCheckResult:
        """Check if spread is acceptable."""
        if not entry_price or not ltp:
            return RiskCheckResult(passed=True, message="No spread check needed")
        
        spread_pct = abs(entry_price - ltp) / ltp * 100
        
        if spread_pct > max_spread_pct:
            return RiskCheckResult(
                passed=False,
                message=f"Spread too high: {spread_pct:.2f}%"
            )
        
        return RiskCheckResult(
            passed=True,
            message=f"Spread OK: {spread_pct:.2f}%"
        )
    
    def check_stale_signal(self, signal_time, max_age_minutes: int = 30) -> RiskCheckResult:
        """Check if signal is too old."""
        from datetime import datetime, timezone
        
        if not signal_time:
            return RiskCheckResult(passed=True, message="No timestamp")
        
        if isinstance(signal_time, str):
            signal_time = datetime.fromisoformat(signal_time.replace('Z', '+00:00'))
        
        now = datetime.now(timezone.utc)
        age = (now - signal_time).total_seconds() / 60
        
        if age > max_age_minutes:
            return RiskCheckResult(
                passed=False,
                message=f"Signal stale: {age:.0f} minutes old"
            )
        
        return RiskCheckResult(
            passed=True,
            message=f"Signal fresh: {age:.0f} minutes old"
        )
    
    def validate_stop_loss(self, entry_price: float, stop_loss: float,
                          option_type: str) -> RiskCheckResult:
        """Validate stop loss is reasonable."""
        if not stop_loss:
            return RiskCheckResult(passed=True, message="No SL provided")
        
        if entry_price:
            sl_distance = abs(entry_price - stop_loss)
            sl_pct = sl_distance / entry_price * 100
            
            min_sl_pct = 0.5
            max_sl_pct = 10.0
            
            if sl_pct < min_sl_pct:
                return RiskCheckResult(
                    passed=False,
                    message=f"SL too tight: {sl_pct:.2f}% (min: {min_sl_pct}%)"
                )
            
            if sl_pct > max_sl_pct:
                return RiskCheckResult(
                    passed=False,
                    message=f"SL too wide: {sl_pct:.2f}% (max: {max_sl_pct}%)"
                )
        
        return RiskCheckResult(passed=True, message="SL distance OK")
    
    def estimate_slippage(self, price: float, quantity: int,
                         order_type: str = 'MARKET') -> float:
        """Estimate slippage based on order size and type."""
        if order_type == 'MARKET':
            slippage_pct = 0.1
        else:
            slippage_pct = 0.05
        
        if quantity > 1000:
            slippage_pct *= 1.5
        elif quantity > 500:
            slippage_pct *= 1.2
        
        return price * slippage_pct / 100
    
    def calculate_risk_reward(self, entry: float, target: float, 
                             stop_loss: float) -> Optional[float]:
        """Calculate risk-reward ratio."""
        if not all([entry, target, stop_loss]):
            return None
        
        risk = abs(entry - stop_loss)
        reward = abs(target - entry)
        
        if risk > 0:
            return reward / risk
        
        return None
    
    def run_all_checks(self, signal_data: dict, market_data: dict,
                       current_positions: int, daily_pnl: float) -> dict:
        """Run all risk checks."""
        checks = {}
        
        checks['daily_loss'] = self.check_max_daily_loss(daily_pnl)
        checks['max_positions'] = self.check_max_positions(current_positions)
        
        entry_price = signal_data.get('entry_price') or market_data.get('ltp')
        ltp = market_data.get('ltp')
        
        if entry_price and ltp:
            checks['spread'] = self.check_spread(entry_price, ltp)
        
        if signal_data.get('stop_loss'):
            checks['sl_valid'] = self.validate_stop_loss(
                entry_price,
                signal_data.get('stop_loss'),
                signal_data.get('option_type')
            )
        
        signal_time = signal_data.get('created_at')
        if signal_time:
            checks['stale'] = self.check_stale_signal(signal_time)
        
        return checks
    
    def get_passed_checks(self, checks: dict) -> bool:
        """Check if all critical checks passed."""
        critical = ['daily_loss', 'max_positions', 'spread']
        
        for key in critical:
            if key in checks and not checks[key].passed:
                return False
        
        return True


risk_engine = RiskEngine()
