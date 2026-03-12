import os
import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Zerodha Trading Bot", version="1.0.0")

# In-memory storage
signals_db = []
positions_db = []
research_db = []

# Kite configuration
KITE_API_KEY = os.getenv("KITE_API_KEY", "3v3h2zkvyqhn163b")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# Try to import kiteconnect
try:
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=KITE_API_KEY)
    if KITE_ACCESS_TOKEN:
        kite.set_access_token(KITE_ACCESS_TOKEN)
    KITE_AVAILABLE = True
except Exception as e:
    print(f"Kite not available: {e}")
    kite = None
    KITE_AVAILABLE = False

@app.get("/")
def root():
    return {
        "name": "Zerodha Trading Bot",
        "version": "1.0.0",
        "status": "running",
        "paper_trading": PAPER_TRADING,
        "kite_connected": KITE_AVAILABLE and bool(KITE_ACCESS_TOKEN),
        "endpoints": [
            "POST /webhook/signal",
            "POST /webhook/research", 
            "GET /api/positions",
            "GET /api/orders",
            "GET /api/holdings",
            "GET /api/margins",
            "POST /api/orders/place",
            "GET /api/kite/login-url",
            "POST /api/kite/set-token"
        ]
    }

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "paper_trading": PAPER_TRADING,
        "kite_connected": KITE_AVAILABLE and bool(KITE_ACCESS_TOKEN)
    }

@app.get("/api/kite/login-url")
def get_login_url():
    """Get Zerodha login URL"""
    if not kite:
        raise HTTPException(status_code=500, detail="Kite not available")
    return {"url": kite.login_url()}

class SetTokenRequest(BaseModel):
    access_token: str

@app.post("/api/kite/set-token")
def set_access_token(request: SetTokenRequest):
    """Set access token after obtaining from Zerodha"""
    global KITE_ACCESS_TOKEN
    KITE_ACCESS_TOKEN = request.access_token
    if kite:
        kite.set_access_token(request.access_token)
    return {"status": "success", "message": "Access token set"}

class SignalInput(BaseModel):
    message: str = ""
    source: str = "webhook"

@app.post("/webhook/signal")
async def receive_signal(data: SignalInput):
    """Receive signal via webhook"""
    signal = {
        "id": len(signals_db) + 1,
        "source": data.source,
        "raw_message": data.message,
        "status": "pending"
    }
    signals_db.append(signal)
    return {"status": "accepted", "signal_id": signal["id"], "message": "Signal received - will be processed when trading is enabled"}

class ResearchInput(BaseModel):
    source: str
    content: str
    parsed_data: dict = None

@app.post("/webhook/research")
async def receive_research(data: ResearchInput):
    """Receive research from external agents"""
    research = {
        "id": len(research_db) + 1,
        "source": data.source,
        "content": data.content,
        "parsed_data": data.parsed_data,
        "validated": False
    }
    research_db.append(research)
    return {"status": "accepted", "research_id": research["id"]}

class OrderRequest(BaseModel):
    symbol: str
    transaction_type: str  # BUY or SELL
    quantity: int
    product: str = "MIS"
    order_type: str = "MARKET"
    price: float = None
    trigger_price: float = None

@app.post("/api/orders/place")
def place_order(order: OrderRequest):
    """Place an order"""
    if PAPER_TRADING:
        order_result = {
            "order_id": f"PAPER_{len(positions_db) + 1}",
            "message": "Paper trade - order placed",
            "symbol": order.symbol,
            "quantity": order.quantity,
            "price": order.price or 0
        }
        positions_db.append({
            "id": len(positions_db) + 1,
            "symbol": order.symbol,
            "quantity": order.quantity,
            "entry_price": order.price or 0,
            "status": "open"
        })
        return order_result
    
    if not kite or not KITE_ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="Kite not configured. Set access token first.")
    
    try:
        order_params = {
            "tradingsymbol": order.symbol,
            "exchange": "NFO" if order.symbol.endswith(('CE', 'PE', 'FUT')) else "NSE",
            "transaction_type": order.transaction_type,
            "quantity": order.quantity,
            "product": order.product,
            "order_type": order.order_type,
            "variety": "regular",
        }
        if order.price:
            order_params["price"] = order.price
        if order.trigger_price:
            order_params["trigger_price"] = order.trigger_price
            
        order_id = kite.place_order(**order_params)
        return {"status": "success", "order_id": order_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/positions")
def get_positions():
    """Get all positions"""
    if PAPER_TRADING:
        return positions_db
    
    if not kite or not KITE_ACCESS_TOKEN:
        return positions_db
    
    try:
        positions = kite.positions()
        return positions.get('net', [])
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/orders")
def get_orders():
    """Get order history"""
    if not kite or not KITE_ACCESS_TOKEN:
        return []
    try:
        return kite.orders()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/holdings")
def get_holdings():
    """Get holdings"""
    if not kite or not KITE_ACCESS_TOKEN:
        return []
    try:
        return kite.holdings()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/margins")
def get_margins():
    """Get account margins"""
    if PAPER_TRADING:
        return {"net": 100000, "available": 100000}
    
    if not kite or not KITE_ACCESS_TOKEN:
        return {"error": "Kite not configured"}
    
    try:
        return kite.margins()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/signals")
def list_signals():
    return signals_db

@app.get("/api/stats")
def get_stats():
    return {
        "total_signals": len(signals_db),
        "total_positions": len(positions_db),
        "total_research": len(research_db),
        "paper_trading": PAPER_TRADING,
        "kite_connected": KITE_AVAILABLE and bool(KITE_ACCESS_TOKEN)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "4444"))
    uvicorn.run(app, host="0.0.0.0", port=port)
