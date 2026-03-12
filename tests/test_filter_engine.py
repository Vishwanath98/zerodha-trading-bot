import pytest
from datetime import datetime, timedelta
from src.services.filter_engine import StrategyFilterEngine


class TestStrategyFilterEngine:
    """Tests for the strategy filter engine."""
    
    def setup_method(self):
        self.engine = StrategyFilterEngine()
    
    def _generate_sample_candles(self, n: int = 30) -> list:
        """Generate sample candle data for testing."""
        import random
        
        base_price = 22500
        candles = []
        
        for i in range(n):
            change = random.uniform(-50, 50)
            open_price = base_price + change
            close_price = open_price + random.uniform(-20, 20)
            high_price = max(open_price, close_price) + random.uniform(0, 10)
            low_price = min(open_price, close_price) - random.uniform(0, 10)
            
            candles.append({
                'date': (datetime.now() - timedelta(minutes=n-i)).isoformat(),
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': random.randint(100000, 500000)
            })
            
            base_price = close_price
        
        return candles
    
    def test_filter_engine_init(self):
        """Test filter engine initialization."""
        assert self.engine.filters_enabled is not None
        assert 'order_block' in self.engine.filters_enabled
        assert 'fibonacci' in self.engine.filters_enabled
    
    def test_enable_filter(self):
        """Test enabling a filter."""
        self.engine.disable_filter('order_block')
        assert self.engine.filters_enabled['order_block'] is False
        
        self.engine.enable_filter('order_block')
        assert self.engine.filters_enabled['order_block'] is True
    
    def test_disable_filter(self):
        """Test disabling a filter."""
        self.engine.disable_filter('fibonacci')
        assert self.engine.filters_enabled['fibonacci'] is False
    
    def test_check_order_block_disabled(self):
        """Test order block check when disabled."""
        self.engine.disable_filter('order_block')
        
        result = self.engine.check_order_block([])
        
        assert result.passed is True
    
    def test_check_fibonacci_disabled(self):
        """Test fibonacci check when disabled."""
        self.engine.disable_filter('fibonacci')
        
        result = self.engine.check_fibonacci([], 22500)
        
        assert result.passed is True
    
    def test_check_ema_disabled(self):
        """Test EMA check when disabled."""
        self.engine.disable_filter('ema')
        
        result = self.engine.check_ema([])
        
        assert result.passed is True
    
    def test_check_candlestick_disabled(self):
        """Test candlestick check when disabled."""
        self.engine.disable_filter('candlestick')
        
        result = self.engine.check_candlestick([])
        
        assert result.passed is True
    
    def test_check_volume_disabled(self):
        """Test volume check when disabled."""
        self.engine.disable_filter('volume')
        
        result = self.engine.check_volume([])
        
        assert result.passed is True
    
    def test_check_vix_disabled(self):
        """Test VIX check when disabled."""
        self.engine.disable_filter('vix')
        
        result = self.engine.check_vix(25.0)
        
        assert result.passed is True
    
    def test_check_vix_ok(self):
        """Test VIX check when OK."""
        result = self.engine.check_vix(15.0)
        
        assert result.passed is True
    
    def test_check_vix_high(self):
        """Test VIX check when high."""
        result = self.engine.check_vix(35.0)
        
        assert result.passed is False
    
    def test_calculate_overall_confidence(self):
        """Test confidence calculation."""
        from src.services.filter_engine import FilterResult
        
        results = {
            'order_block': FilterResult('order_block', True, 0.8, ''),
            'fibonacci': FilterResult('fibonacci', True, 0.6, ''),
            'ema': FilterResult('ema', False, 0.3, ''),
        }
        
        confidence = self.engine.calculate_overall_confidence(results)
        
        assert confidence > 0
        assert confidence < 1
    
    def test_prepare_dataframe(self):
        """Test DataFrame preparation from candles."""
        candles = self._generate_sample_candles(30)
        
        df = self.engine._prepare_dataframe(candles)
        
        assert not df.empty
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns


class TestFilterResults:
    """Test filter result objects."""
    
    def test_filter_result_creation(self):
        """Test creating a filter result."""
        from src.services.filter_engine import FilterResult
        
        result = FilterResult(
            filter_name='test_filter',
            passed=True,
            confidence=0.8,
            details='Test details'
        )
        
        assert result.filter_name == 'test_filter'
        assert result.passed is True
        assert result.confidence == 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
