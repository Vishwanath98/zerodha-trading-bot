import pytest
from src.services.risk_engine import RiskEngine


class TestRiskEngine:
    """Tests for the risk engine."""
    
    def setup_method(self):
        self.engine = RiskEngine()
    
    def test_calculate_position_size(self):
        """Test position size calculation."""
        quantity = self.engine.calculate_position_size(
            entry_price=22550,
            stop_loss=22500,
            account_balance=100000
        )
        
        assert quantity >= 1
    
    def test_calculate_position_size_no_sl(self):
        """Test position size with no stop loss."""
        quantity = self.engine.calculate_position_size(
            entry_price=22550,
            stop_loss=None,
            account_balance=100000
        )
        
        assert quantity == self.engine.default_quantity
    
    def test_check_max_daily_loss_not_hit(self):
        """Test max daily loss not hit."""
        result = self.engine.check_max_daily_loss(-5000)
        
        assert result.passed is True
    
    def test_check_max_daily_loss_hit(self):
        """Test max daily loss hit."""
        result = self.engine.check_max_daily_loss(-15000)
        
        assert result.passed is False
    
    def test_check_max_positions_ok(self):
        """Test max positions not hit."""
        result = self.engine.check_max_positions(3)
        
        assert result.passed is True
    
    def test_check_max_positions_full(self):
        """Test max positions hit."""
        result = self.engine.check_max_positions(5)
        
        assert result.passed is False
    
    def test_check_spread_ok(self):
        """Test spread check passes."""
        result = self.engine.check_spread(22550, 22550)
        
        assert result.passed is True
    
    def test_check_spread_too_high(self):
        """Test spread too high."""
        result = self.engine.check_spread(22550, 22800)
        
        assert result.passed is False
    
    def test_validate_stop_loss_reasonable(self):
        """Test stop loss validation passes."""
        result = self.engine.validate_stop_loss(22550, 22400, "CE")
        
        assert result.passed is True
    
    def test_validate_stop_loss_too_tight(self):
        """Test stop loss too tight."""
        result = self.engine.validate_stop_loss(22550, 22545, "CE")
        
        assert result.passed is False
    
    def test_validate_stop_loss_too_wide(self):
        """Test stop loss too wide."""
        result = self.engine.validate_stop_loss(22550, 20000, "CE")
        
        assert result.passed is False
    
    def test_calculate_risk_reward(self):
        """Test risk-reward calculation."""
        rr = self.engine.calculate_risk_reward(22550, 22650, 22500)
        
        assert rr is not None
        assert rr > 0
    
    def test_get_passed_checks_all_pass(self):
        """Test passed checks when all pass."""
        checks = {
            'daily_loss': type('obj', (object,), {'passed': True})(),
            'max_positions': type('obj', (object,), {'passed': True})(),
            'spread': type('obj', (object,), {'passed': True})(),
        }
        
        assert self.engine.get_passed_checks(checks) is True
    
    def test_get_passed_checks_one_fail(self):
        """Test passed checks when one fails."""
        checks = {
            'daily_loss': type('obj', (object,), {'passed': True})(),
            'max_positions': type('obj', (object,), {'passed': False})(),
            'spread': type('obj', (object,), {'passed': True})(),
        }
        
        assert self.engine.get_passed_checks(checks) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
