from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass
from kiteconnect import KiteApp
from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str]
    message: str
    average_price: Optional[float] = None


class ZerodhaExecutor:
    """
    Zerodha Kite Connect API executor for placing orders.
    """
    
    def __init__(self, api_key: str = None, access_token: str = None):
        self.api_key = api_key or settings.kite_api_key
        self.access_token = access_token or settings.kite_access_token
        self.paper_trading = settings.paper_trading
        
        if self.api_key and self.access_token:
            self.kite = KiteApp(api_key=self.api_key, access_token=self.access_token)
        else:
            self.kite = None
            logger.warning("Zerodha client not initialized - missing credentials")
    
    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                   product: str = 'MIS', order_type: str = 'MARKET',
                   price: Optional[float] = None,
                   trigger_price: Optional[float] = None,
                   stop_loss: Optional[float] = None) -> OrderResult:
        """Place a single order."""
        if self.paper_trading:
            logger.info(f"[PAPER] Would place order: {symbol} {transaction_type} qty={quantity}")
            return OrderResult(
                success=True,
                order_id=f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                message="Paper trade order placed",
                average_price=price
            )
        
        if not self.kite:
            return OrderResult(success=False, order_id=None, message="Kite not initialized")
        
        try:
            exchange = "NSE"
            if symbol.endswith('CE') or symbol.endswith('PE'):
                exchange = "NFO"
            
            order_params = {
                "tradingsymbol": symbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "product": product,
                "order_type": order_type,
            }
            
            if price:
                order_params["price"] = price
            
            if trigger_price:
                order_params["trigger_price"] = trigger_price
            
            if stop_loss and transaction_type == "BUY":
                order_params["squareoff"] = str(stop_loss)
                order_params["trailing_stoploss"] = 1
            
            order_id = self.kite.place_order(**order_params)
            
            logger.info(f"Order placed: {order_id} - {symbol} {transaction_type}")
            
            return OrderResult(
                success=True,
                order_id=order_id,
                message="Order placed successfully"
            )
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return OrderResult(success=False, order_id=None, message=str(e))
    
    def place_market_order(self, symbol: str, transaction_type: str,
                          quantity: int, product: str = 'MIS') -> OrderResult:
        """Place a market order."""
        return self.place_order(
            symbol, transaction_type, quantity, product, 'MARKET'
        )
    
    def place_limit_order(self, symbol: str, transaction_type: str,
                         quantity: int, price: float,
                         product: str = 'MIS') -> OrderResult:
        """Place a limit order."""
        return self.place_order(
            symbol, transaction_type, quantity, product, 'LIMIT', price
        )
    
    def place_stoploss_order(self, symbol: str, transaction_type: str,
                            quantity: int, trigger_price: float,
                            product: str = 'MIS') -> OrderResult:
        """Place a stoploss order."""
        return self.place_order(
            symbol, transaction_type, quantity, product, 'SL', 
            trigger_price=trigger_price
        )
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order."""
        if self.paper_trading:
            return OrderResult(
                success=True,
                order_id=order_id,
                message="Paper trade: order cancelled"
            )
        
        try:
            self.kite.cancel_order(order_id)
            return OrderResult(success=True, order_id=order_id, message="Order cancelled")
        except Exception as e:
            return OrderResult(success=False, order_id=order_id, message=str(e))
    
    def get_order(self, order_id: str) -> Optional[dict]:
        """Get order details."""
        if self.paper_trading:
            return {"order_id": order_id, "status": "COMPLETED"}
        
        try:
            return self.kite.order_history(order_id)[-1]
        except Exception as e:
            logger.error(f"Error fetching order: {e}")
            return None
    
    def get_positions(self) -> List[dict]:
        """Get all positions."""
        if self.paper_trading:
            return []
        
        try:
            positions = self.kite.positions()
            return positions.get('net', [])
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def get_holdings(self) -> List[dict]:
        """Get holdings."""
        if self.paper_trading:
            return []
        
        try:
            return self.kite.holdings()
        except Exception as e:
            logger.error(f"Error fetching holdings: {e}")
            return []
    
    def get_quote(self, symbol: str) -> Optional[dict]:
        """Get quote for symbol."""
        if self.paper_trading:
            return {"last_price": 0}
        
        try:
            quotes = self.kite.quote(f"NSE:{symbol}")
            return quotes.get(f"NSE:{symbol}")
        except Exception as e:
            logger.error(f"Error fetching quote: {e}")
            return None
    
    def get_margin(self) -> Optional[dict]:
        """Get account margin."""
        if self.paper_trading:
            return {"net": 100000, "available": 100000}
        
        try:
            return self.kite.margins()
        except Exception as e:
            logger.error(f"Error fetching margin: {e}")
            return None
    
    def get_instruments(self, exchange: str = "NSE") -> List[dict]:
        """Get instruments list."""
        if self.paper_trading:
            return []
        
        try:
            return self.kite.instruments(exchange)
        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            return []


executor = ZerodhaExecutor()
