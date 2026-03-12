import json
import redis.asyncio as redis
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()


class InstrumentResolver:
    """Resolves trading symbols to Zerodha instrument tokens."""
    
    EXCHANGE_MAP = {
        'NIFTY': 'NSE',
        'BANKNIFTY': 'NSE',
        'FINNIFTY': 'NSE',
        'RELIANCE': 'NSE',
        'INFY': 'NSE',
        'TCS': 'NSE',
    }
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.instruments_cache_key = "instruments:all"
        self._instruments: Dict[str, dict] = {}
    
    async def load_instruments(self, instruments_data: List[dict]) -> None:
        """Load instruments into cache."""
        self._instruments.clear()
        for inst in instruments_data:
            token = str(inst.get('instrument_token'))
            self._instruments[token] = inst
            
            symbol = inst.get('tradingsymbol', '')
            self._instruments[symbol] = inst
            
            underlying = inst.get('underlying')
            if underlying:
                self._instruments[underlying] = inst
        
        await self.redis.set(
            self.instruments_cache_key,
            json.dumps(self._instruments),
            ex=3600
        )
        logger.info(f"Loaded {len(self._instruments)} instruments")
    
    async def get_instrument(self, underlying: str, strike: Optional[int], 
                            option_type: Optional[str], expiry: Optional[str] = None) -> Optional[dict]:
        """Get instrument details for a trading symbol."""
        cache_key = f"instrument:{underlying}:{strike}:{option_type}:{expiry}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        for token, inst in self._instruments.items():
            if isinstance(inst, dict):
                symbol = inst.get('tradingsymbol', '').upper()
                
                if underlying.upper() in symbol:
                    if option_type:
                        if strike and str(strike) in symbol and option_type.upper() in symbol:
                            if expiry:
                                exp_str = inst.get('expiry', '')
                                if expiry.lower() in exp_str.lower():
                                    await self.redis.set(cache_key, json.dumps(inst), ex=300)
                                    return inst
                            else:
                                await self.redis.set(cache_key, json.dumps(inst), ex=300)
                                return inst
        
        logger.warning(f"Instrument not found: {underlying} {strike} {option_type}")
        return None
    
    def generate_symbol(self, underlying: str, strike: int, option_type: str, 
                       expiry: Optional[str] = None) -> str:
        """Generate trading symbol."""
        base = underlying.upper()
        if option_type:
            if expiry:
                return f"{base}{expiry.upper()}{strike}{option_type.upper()}"
            return f"{base}{strike}{option_type.upper()}"
        return base
    
    async def find_nearest_strike(self, underlying: str, price: float, 
                                  option_type: str, direction: str = 'below') -> Optional[int]:
        """Find nearest strike price to given price."""
        strikes = []
        
        for token, inst in self._instruments.items():
            if isinstance(inst, dict):
                symbol = inst.get('tradingsymbol', '').upper()
                if underlying.upper() in symbol and option_type.upper() in symbol:
                    strike = inst.get('strike')
                    if strike:
                        strikes.append(int(strike))
        
        if not strikes:
            return None
        
        strikes.sort()
        
        if direction == 'below':
            return max([s for s in strikes if s <= price], default=None)
        else:
            return min([s for s in strikes if s >= price], default=None)


class MarketDataService:
    """Fetches and caches market data."""
    
    def __init__(self, kite_client, redis_client: redis.Redis):
        self.kite = kite_client
        self.redis = redis_client
    
    async def get_ltp(self, instrument_token: str) -> Optional[float]:
        """Get Last Traded Price."""
        cache_key = f"ltp:{instrument_token}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return float(cached)
        
        try:
            ltp = self.kite.ltp(instrument_token)
            if ltp:
                price = ltp.get(instrument_token, {}).get('last_price')
                if price:
                    await self.redis.set(cache_key, str(price), ex=10)
                    return price
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
        
        return None
    
    async def get_ohlc(self, instrument_token: str, interval: str = "day") -> Optional[dict]:
        """Get OHLC data."""
        cache_key = f"ohlc:{instrument_token}:{interval}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            candles = self.kite.ohlc(instrument_token)
            if candles:
                data = candles.get(instrument_token, {})
                await self.redis.set(cache_key, json.dumps(data), ex=60)
                return data
        except Exception as e:
            logger.error(f"Error fetching OHLC: {e}")
        
        return None
    
    async def get_candles(self, instrument_token: str, from_date: datetime, 
                         to_date: datetime, interval: str = "5minute") -> Optional[List]:
        """Get historical candle data."""
        cache_key = f"candles:{instrument_token}:{interval}:{from_date.date()}:{to_date.date()}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            candles = self.kite.historical_data(
                instrument_token,
                from_date.isoformat(),
                to_date.isoformat(),
                interval
            )
            if candles:
                await self.redis.set(cache_key, json.dumps(candles), ex=60)
                return candles
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
        
        return None
    
    async def get_option_chain(self, underlying: str, expiry_date: Optional[datetime] = None) -> List[dict]:
        """Get option chain for underlying."""
        cache_key = f"option_chain:{underlying}"
        
        if expiry_date:
            cache_key = f"option_chain:{underlying}:{expiry_date.date()}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            instruments = self.kite.instruments("NSE")
            options = []
            
            for inst in instruments:
                if inst.get('underlying') == underlying:
                    if expiry_date:
                        inst_expiry = inst.get('expiry')
                        if inst_expiry and inst_expiry.date() == expiry_date.date():
                            options.append(inst)
                    else:
                        options.append(inst)
            
            await self.redis.set(cache_key, json.dumps(options), ex=300)
            return options
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
        
        return []
    
    async def get_vix(self) -> Optional[float]:
        """Get India VIX value."""
        cache_key = "vix:current"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return float(cached)
        
        try:
            quotes = self.kite.quote("NSE:INDIAVIX")
            if quotes:
                vix = quotes.get('NSE:INDIAVIX', {}).get('last_price')
                if vix:
                    await self.redis.set(cache_key, str(vix), ex=60)
                    return vix
        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
        
        return None
    
    async def get_oi_data(self, instrument_token: str) -> Optional[dict]:
        """Get Open Interest data."""
        cache_key = f"oi:{instrument_token}"
        
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        try:
            oi_data = self.kite.ohlc(instrument_token)
            if oi_data:
                await self.redis.set(cache_key, json.dumps(oi_data), ex=60)
                return oi_data
        except Exception as e:
            logger.error(f"Error fetching OI: {e}")
        
        return None
