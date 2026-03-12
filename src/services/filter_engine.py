from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from src.core.logger import logger


def calculate_ema(prices: List[float], period: int) -> float:
    """Calculate EMA for a list of prices."""
    if len(prices) < period:
        return 0.0
    
    prices_array = np.array(prices)
    ema = float(prices_array[0])
    multiplier = 2 / (period + 1)
    
    for price in prices_array[1:]:
        ema = (float(price) - ema) * multiplier + ema
    
    return ema


@dataclass
class FilterResult:
    filter_name: str
    passed: bool
    confidence: float
    details: str


class StrategyFilterEngine:
    """
    Technical analysis filters for signal validation.
    Supports: Order Block, Fibonacci, EMA, Candlesticks, Trendlines, Volume
    """
    
    def __init__(self):
        self.filters_enabled = {
            'order_block': True,
            'fibonacci': True,
            'ema': True,
            'candlestick': True,
            'trendline': True,
            'volume': True,
            'vix': True,
        }
        
        self.settings = {
            'fib_levels': [0.236, 0.382, 0.5, 0.618, 0.786],
            'ema_fast': 9,
            'ema_medium': 21,
            'ema_slow': 50,
            'ema_super': 200,
            'vix_threshold': 20.0,
            'volume_multiplier': 1.5,
        }
    
    def enable_filter(self, filter_name: str):
        self.filters_enabled[filter_name] = True
    
    def disable_filter(self, filter_name: str):
        self.filters_enabled[filter_name] = False
    
    def set_filter_settings(self, filter_name: str, settings: dict):
        self.settings.update(settings)
    
    def _prepare_dataframe(self, candles: List[dict]) -> pd.DataFrame:
        """Convert candles to DataFrame."""
        if not candles:
            return pd.DataFrame()
        
        df = pd.DataFrame(candles)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        df = df.sort_index()
        
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def check_order_block(self, candles: List[dict], direction: str = 'bullish') -> FilterResult:
        """
        Detect Order Blocks - areas of institutional activity.
        Bullish OB: Large green candle followed by consolidation
        Bearish OB: Large red candle followed by consolidation
        """
        if not self.filters_enabled.get('order_block', False):
            return FilterResult('order_block', True, 1.0, 'Disabled')
        
        try:
            df = self._prepare_dataframe(candles)
            if len(df) < 20:
                return FilterResult('order_block', False, 0.0, 'Insufficient data')
            
            df['body'] = abs(df['close'] - df['open'])
            df['range'] = df['high'] - df['low']
            df['body_pct'] = df['body'] / df['range']
            
            recent = df.tail(5)
            avg_body = recent['body'].mean()
            
            for i in range(len(recent) - 2, -1, -1):
                candle = recent.iloc[i]
                if direction == 'bullish':
                    if candle['close'] > candle['open'] and candle['body'] > avg_body * 1.5:
                        low = candle['low']
                        subsequent = recent.iloc[i+1:]
                        if all(subsequent['low'] >= low * 0.995):
                            return FilterResult(
                                'order_block', True, 0.8,
                                f'Bullish OB found at {low}'
                            )
                else:
                    if candle['close'] < candle['open'] and candle['body'] > avg_body * 1.5:
                        high = candle['high']
                        subsequent = recent.iloc[i+1:]
                        if all(subsequent['high'] <= high * 1.005):
                            return FilterResult(
                                'order_block', True, 0.8,
                                f'Bearish OB found at {high}'
                            )
            
            return FilterResult('order_block', False, 0.3, 'No OB found')
            
        except Exception as e:
            logger.error(f"Order block check error: {e}")
            return FilterResult('order_block', False, 0.0, str(e))
    
    def check_fibonacci(self, candles: List[dict], current_price: float, 
                       direction: str = 'long') -> FilterResult:
        """
        Check if price is at Fibonacci support/resistance level.
        """
        if not self.filters_enabled.get('fibonacci', False):
            return FilterResult('fibonacci', True, 1.0, 'Disabled')
        
        try:
            df = self._prepare_dataframe(candles)
            if len(df) < 50:
                return FilterResult('fibonacci', False, 0.0, 'Insufficient data')
            
            high = df['high'].tail(50).max()
            low = df['high'].tail(50).min()
            diff = high - low
            
            levels = self.settings['fib_levels']
            fib_prices = [low + l * diff for l in levels]
            
            for fib_price in fib_prices:
                tolerance = diff * 0.01
                if abs(current_price - fib_price) < tolerance:
                    return FilterResult(
                        'fibonacci', True, 0.7,
                        f'Near fib level {fib_price:.2f}'
                    )
            
            return FilterResult('fibonacci', False, 0.4, 'Not near fib level')
            
        except Exception as e:
            logger.error(f"Fibonacci check error: {e}")
            return FilterResult('fibonacci', False, 0.0, str(e))
    
    def check_ema(self, candles: List[dict], direction: str = 'long') -> FilterResult:
        """
        Check EMA crossovers and trends.
        """
        if not self.filters_enabled.get('ema', False):
            return FilterResult('ema', True, 1.0, 'Disabled')
        
        try:
            if len(candles) < 50:
                return FilterResult('ema', False, 0.0, 'Insufficient data')
            
            fast = self.settings['ema_fast']
            medium = self.settings['ema_medium']
            slow = self.settings['ema_slow']
            
            close_prices = [c['close'] for c in candles]
            
            ema_fast = calculate_ema(close_prices, fast)
            ema_medium = calculate_ema(close_prices, medium)
            ema_slow = calculate_ema(close_prices, slow)
            
            if not all([ema_fast, ema_medium, ema_slow]):
                return FilterResult('ema', False, 0.0, 'Cannot calculate EMA')
            
            current_price = close_prices[-1]
            
            if direction == 'long':
                if ema_fast > ema_medium > ema_slow:
                    return FilterResult('ema', True, 0.8, 'Bullish EMA alignment')
                elif current_price > ema_slow:
                    return FilterResult('ema', True, 0.6, 'Above slow EMA')
            else:
                if ema_fast < ema_medium < ema_slow:
                    return FilterResult('ema', True, 0.8, 'Bearish EMA alignment')
                elif current_price < ema_slow:
                    return FilterResult('ema', True, 0.6, 'Below slow EMA')
            
            return FilterResult('ema', False, 0.3, 'No EMA confirmation')
            
        except Exception as e:
            logger.error(f"EMA check error: {e}")
            return FilterResult('ema', False, 0.0, str(e))
    
    def check_candlestick(self, candles: List[dict], direction: str = 'long') -> FilterResult:
        """
        Check for bullish/bearish candlestick patterns.
        """
        if not self.filters_enabled.get('candlestick', False):
            return FilterResult('candlestick', True, 1.0, 'Disabled')
        
        try:
            df = self._prepare_dataframe(candles)
            if len(df) < 5:
                return FilterResult('candlestick', False, 0.0, 'Insufficient data')
            
            last = df.iloc[-1]
            body = abs(last['close'] - last['open'])
            upper_shadow = last['high'] - max(last['open'], last['close'])
            lower_shadow = min(last['open'], last['close']) - last['low']
            total_range = last['high'] - last['low']
            
            is_bullish = last['close'] > last['open']
            
            if total_range > 0:
                body_ratio = body / total_range
                upper_ratio = upper_shadow / total_range
                lower_ratio = lower_shadow / total_range
                
                if direction == 'long' and is_bullish:
                    if lower_ratio > 0.5:
                        return FilterResult('candlestick', True, 0.8, 'Hammer pattern')
                    if body_ratio > 0.7:
                        return FilterResult('candlestick', True, 0.7, 'Bullish candle')
                    return FilterResult('candlestick', True, 0.5, 'Weak bullish')
                
                elif direction == 'short' and not is_bullish:
                    if upper_ratio > 0.5:
                        return FilterResult('candlestick', True, 0.8, 'Shooting star')
                    if body_ratio > 0.7:
                        return FilterResult('candlestick', True, 0.7, 'Bearish candle')
                    return FilterResult('candlestick', True, 0.5, 'Weak bearish')
            
            return FilterResult('candlestick', False, 0.3, 'No clear pattern')
            
        except Exception as e:
            logger.error(f"Candlestick check error: {e}")
            return FilterResult('candlestick', False, 0.0, str(e))
    
    def check_volume(self, candles: List[dict]) -> FilterResult:
        """
        Check for unusual volume.
        """
        if not self.filters_enabled.get('volume', False):
            return FilterResult('volume', True, 1.0, 'Disabled')
        
        try:
            df = self._prepare_dataframe(candles)
            if len(df) < 20:
                return FilterResult('volume', False, 0.0, 'Insufficient data')
            
            avg_volume = df['volume'].tail(20).mean()
            last_volume = df.iloc[-1]['volume']
            
            multiplier = self.settings['volume_multiplier']
            
            if last_volume > avg_volume * multiplier:
                return FilterResult(
                    'volume', True, 0.7,
                    f'High volume: {last_volume/avg_volume:.1f}x avg'
                )
            
            return FilterResult('volume', True, 0.5, 'Normal volume')
            
        except Exception as e:
            logger.error(f"Volume check error: {e}")
            return FilterResult('volume', False, 0.0, str(e))
    
    def check_vix(self, vix_value: float, max_threshold: Optional[float] = None) -> FilterResult:
        """
        Check VIX level for volatility regime.
        """
        if not self.filters_enabled.get('vix', False):
            return FilterResult('vix', True, 1.0, 'Disabled')
        
        threshold = max_threshold or self.settings['vix_threshold']
        
        if vix_value <= threshold:
            return FilterResult('vix', True, 0.8, f'VIX OK: {vix_value:.2f}')
        elif vix_value <= threshold * 1.5:
            return FilterResult('vix', True, 0.5, f'Higher VIX: {vix_value:.2f}')
        
        return FilterResult('vix', False, 0.2, f'VIX too high: {vix_value:.2f}')
    
    def run_all_filters(self, candles: List[dict], vix: float, 
                       direction: str = 'long') -> Dict[str, FilterResult]:
        """Run all enabled filters."""
        results = {}
        
        results['order_block'] = self.check_order_block(candles, direction)
        results['fibonacci'] = self.check_fibonacci(candles, 
            candles[-1]['close'] if candles else 0, direction)
        results['ema'] = self.check_ema(candles, direction)
        results['candlestick'] = self.check_candlestick(candles, direction)
        results['volume'] = self.check_volume(candles)
        results['vix'] = self.check_vix(vix)
        
        return results
    
    def calculate_overall_confidence(self, results: Dict[str, FilterResult]) -> float:
        """Calculate overall filter confidence score."""
        enabled_results = [r for r in results.values() if r.filter_name != 'vix']
        
        if not enabled_results:
            return 0.0
        
        passed_count = sum(1 for r in enabled_results if r.passed)
        avg_confidence = sum(r.confidence for r in enabled_results) / len(enabled_results)
        
        return (passed_count / len(enabled_results)) * avg_confidence


filter_engine = StrategyFilterEngine()
