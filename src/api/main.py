import os
import json
import re
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

# ============= CONFIG =============
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "false").lower() == "true"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

DB_TYPE = os.getenv("DB_TYPE", "sqlite")

# ============= DATABASE =============
if DB_TYPE == "postgres":
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    def get_db_connection():
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "tradingbot"),
            password=os.getenv("POSTGRES_PASSWORD", "tradingbot"),
            database=os.getenv("POSTGRES_DB", "tradingbot")
        )
    
    def init_db():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                order_id TEXT,
                symbol TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL,
                status TEXT,
                pnl REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                trade_action TEXT,
                confirmed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
        cur.close()
        conn.close()
    
    def log_chat(user_msg: str, bot_msg: str, trade_action: str = None):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO chat_history (user_message, bot_response, trade_action) VALUES (%s, %s, %s)", (user_msg, bot_msg, trade_action))
        conn.commit()
        cur.close()
        conn.close()
    
    def log_trade(order_id: str, symbol: str, transaction_type: str, quantity: int, price: float, status: str):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO trades (order_id, symbol, transaction_type, quantity, price, status) VALUES (%s, %s, %s, %s, %s, %s)", (order_id, symbol, transaction_type, quantity, price, status))
        conn.commit()
        cur.close()
        conn.close()
    
    def get_trade_metrics(days: int = 30):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT * FROM trades WHERE closed_at >= NOW() - INTERVAL '{days} days' ORDER BY closed_at DESC LIMIT 100")
        trades = cur.fetchall()
        cur.close()
        conn.close()
        if not trades:
            return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
        wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        return {"total_trades": len(trades), "wins": wins, "losses": len(trades)-wins, "win_rate": round(wins/len(trades)*100,2), "total_pnl": total_pnl}
    
    def get_chat_history(limit: int = 20):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM chat_history ORDER BY created_at DESC LIMIT %s", (limit,))
        chats = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(c) for c in chats]
else:
    DB_PATH = os.getenv("DB_PATH", "trading_bot.db")
    
    def get_db_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db():
        conn = get_db_connection()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, order_id TEXT, symbol TEXT, transaction_type TEXT, quantity INTEGER, price REAL, status TEXT, pnl REAL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, closed_at TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY, user_message TEXT, bot_response TEXT, trade_action TEXT, confirmed INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        ''')
        conn.commit()
        conn.close()
    
    def log_chat(user_msg: str, bot_msg: str, trade_action: str = None):
        conn = get_db_connection()
        conn.execute("INSERT INTO chat_history (user_message, bot_response, trade_action) VALUES (?, ?, ?)", (user_msg, bot_msg, trade_action))
        conn.commit()
        conn.close()
    
    def log_trade(order_id: str, symbol: str, transaction_type: str, quantity: int, price: float, status: str):
        conn = get_db_connection()
        conn.execute("INSERT INTO trades (order_id, symbol, transaction_type, quantity, price, status) VALUES (?, ?, ?, ?, ?, ?)", (order_id, symbol, transaction_type, quantity, price, status))
        conn.commit()
        conn.close()
    
    def get_trade_metrics(days: int = 30):
        conn = get_db_connection()
        trades = conn.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY closed_at DESC LIMIT 100").fetchall()
        conn.close()
        if not trades:
            return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
        wins = sum(1 for t in trades if t['pnl'] > 0)
        total_pnl = sum(t['pnl'] for t in trades)
        return {"total_trades": len(trades), "wins": wins, "losses": len(trades)-wins, "win_rate": round(wins/len(trades)*100,2), "total_pnl": total_pnl}
    
    def get_chat_history(limit: int = 20):
        conn = get_db_connection()
        chats = conn.execute("SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(c) for c in chats]

init_db()

# ============= KITE =============
kite = None
if KITE_ACCESS_TOKEN:
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=KITE_API_KEY)
        kite.set_access_token(KITE_ACCESS_TOKEN)
    except:
        pass

def get_kite_connected():
    return kite is not None and bool(KITE_ACCESS_TOKEN)

trade_queue = []

class ChatMessage(BaseModel):
    message: str

class QueueConfirm(BaseModel):
    queue_id: int
    action: str

class SignalInput(BaseModel):
    message: str = ""
    source: str = "webhook"

def get_positions() -> List[Dict]:
    if not get_kite_connected():
        return []
    try:
        return kite.positions().get('net', [])
    except:
        return []

def get_margins() -> Dict:
    if PAPER_TRADING:
        return {"equity": {"available": {"live_balance": 100000}}}
    if not get_kite_connected():
        return {"error": "Not connected"}
    try:
        return kite.margins()
    except:
        return {"error": "Failed"}

def get_orders() -> List[Dict]:
    if not get_kite_connected():
        return []
    try:
        return kite.orders()
    except:
        return []

class SmartChatParser:
    def __init__(self):
        self.known_symbols = {}
    
    def update_positions(self, positions: List[Dict]):
        self.known_symbols = {}
        for p in positions:
            symbol = p.get('tradingsymbol', '')
            if symbol:
                self.known_symbols[symbol.lower()] = symbol
    
    def parse(self, message: str, positions: List[Dict]) -> Dict:
        msg = message.lower().strip()
        
        if 'position' in msg or 'holding' in msg:
            return self._handle_position_query(positions, msg)
        if 'pnl' in msg or 'profit' in msg or 'loss' in msg:
            return self._handle_pnl_query(positions)
        if 'buy' in msg or 'sell' in msg:
            return self._handle_trade_request(msg, positions)
        if 'exit' in msg or 'close' in msg:
            return self._handle_exit_request(msg, positions)
        if 'metric' in msg or 'stat' in msg:
            return {"type": "info", "message": "metrics_query"}
        return {"type": "info", "message": "general_query"}
    
    def _handle_position_query(self, positions: List[Dict], msg: str) -> Dict:
        if not positions:
            return {"type": "response", "message": "No open positions."}
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        return {"type": "response", "message": f"{full_symbol}: {p.get('quantity', 0)} qty @ ₹{p.get('average_price', 0)}, P&L: ₹{p.get('pnl', 0):.2f}"}
        text = "📊 Positions:\n" + "\n".join([f"• {p.get('tradingsymbol')}: {p.get('quantity', 0)} @ ₹{p.get('average_price', 0)} | ₹{p.get('pnl', 0):.2f}" for p in positions[:10] if p.get('quantity', 0) != 0])
        return {"type": "response", "message": text}
    
    def _handle_pnl_query(self, positions: List[Dict]) -> Dict:
        total_pnl = sum(p.get('pnl', 0) for p in positions)
        return {"type": "response", "message": f"📈 Today's P&L: ₹{total_pnl:.2f}"}
    
    def _handle_trade_request(self, msg: str, positions: List[Dict]) -> Dict:
        is_buy = 'buy' in msg
        transaction_type = "BUY" if is_buy else "SELL"
        symbol = None
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                symbol = full_symbol
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        return {"type": "trade_request", "message": f"Add to {full_symbol}?", "symbol": full_symbol, "transaction_type": transaction_type, "quantity": abs(p.get('quantity', 0)), "order_type": "MARKET"}
                break
        if not symbol:
            return {"type": "needs_more", "message": "Which symbol? Say 'buy NIFTY' or 'add to SENSEX'"}
        return {"type": "trade_request", "message": f"{transaction_type} {symbol}?", "symbol": symbol, "transaction_type": transaction_type, "quantity": 1, "order_type": "MARKET"}
    
    def _handle_exit_request(self, msg: str, positions: List[Dict]) -> Dict:
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        qty = p.get('quantity', 0)
                        return {"type": "trade_request", "message": f"Exit {full_symbol}?", "symbol": full_symbol, "transaction_type": "SELL" if qty > 0 else "BUY", "quantity": abs(qty), "order_type": "MARKET"}
        if 'all' in msg:
            return {"type": "confirm_action", "message": "⚠️ Exit ALL positions?", "action": "exit_all"}
        return {"type": "needs_more", "message": "Which position to exit?"}

parser = SmartChatParser()

def call_ollama(prompt: str) -> Optional[str]:
    try:
        import requests
        r = requests.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=30)
        if r.status_code == 200:
            return r.json().get('response', '').strip()
    except:
        pass
    return None

def build_context(positions: List[Dict], metrics: Dict) -> str:
    ctx = "Positions:\n"
    for p in positions:
        if p.get('quantity', 0) != 0:
            ctx += f"- {p.get('tradingsymbol')}: {p.get('quantity')} @ ₹{p.get('average_price', 0)}, P&L: ₹{p.get('pnl', 0)}\n"
    ctx += f"\nMetrics: {metrics.get('total_trades', 0)} trades, {metrics.get('win_rate', 0)}% win rate, ₹{metrics.get('total_pnl', 0):.2f} P&L"
    return ctx

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 Trading Bot Started | DB: {DB_TYPE} | Kite: {get_kite_connected()}")
    yield

app = FastAPI(title="Zerodha Trading Bot", version="2.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root():
    return {"name": "Zerodha Trading Bot", "version": "2.1.0", "status": "running", "db_type": DB_TYPE, "kite_connected": get_kite_connected()}

@app.get("/api/stats")
async def get_stats():
    positions = get_positions()
    margins = get_margins()
    daily_pnl = sum(p.get('pnl', 0) for p in positions)
    return {"daily_pnl": daily_pnl, "available_margin": margins.get('equity', {}).get('available', {}).get('live_balance', 0), "open_positions": len([p for p in positions if p.get('quantity', 0) != 0]), "kite_connected": get_kite_connected(), "paper_trading": PAPER_TRADING}

@app.get("/api/positions")
async def get_positions_api():
    return get_positions()

@app.get("/api/orders")
async def get_orders_api():
    return get_orders()

@app.get("/api/metrics")
async def get_metrics(days: int = 30):
    return get_trade_metrics(days)

@app.get("/api/chat-history")
async def get_chat(limit: int = 20):
    return get_chat_history(limit)

@app.get("/api/queue")
async def get_queue():
    return trade_queue

@app.post("/api/chat")
async def chat(message: ChatMessage):
    msg = message.message.strip()
    positions = get_positions()
    parser.update_positions(positions)
    metrics = get_trade_metrics()
    
    parsed = parser.parse(msg, positions)
    response_text = ""
    trade_request = None
    
    if parsed["type"] == "response":
        response_text = parsed["message"]
    elif parsed["type"] == "needs_more":
        context = build_context(positions, metrics)
        ollama_response = call_ollama(f"{context}\n\nUser: {msg}\n\nHelp.")
        response_text = ollama_response or parsed["message"]
    elif parsed["type"] == "trade_request":
        trade_data = {"id": len(trade_queue) + 1, **parsed}
        trade_queue.append(trade_data)
        response_text = f"📋 {parsed['message']}\n\nConfirm in queue."
        trade_request = trade_data
    elif parsed["type"] == "confirm_action" and parsed.get("action") == "exit_all":
        trade_queue.append({"id": len(trade_queue) + 1, "action": "exit_all", "message": "Exit ALL?"})
        response_text = "⚠️ Exit ALL added to queue."
    else:
        context = build_context(positions, metrics)
        ollama_response = call_ollama(f"{context}\n\nUser: {msg}\n\nRespond.")
        response_text = ollama_response or "Try 'show my positions' or 'what's my pnl'."
    
    log_chat(msg, response_text, json.dumps(trade_request) if trade_request else None)
    return {"response": response_text, "trade_request": trade_request}

@app.post("/api/queue/confirm")
async def confirm_trade(request: QueueConfirm):
    trade = next((t for t in trade_queue if t.get("id") == request.queue_id), None)
    if not trade:
        return {"success": False, "message": "Trade not found"}
    
    if request.action == "confirm":
        if trade.get("action") == "exit_all":
            positions = get_positions()
            exited = []
            for p in positions:
                if p.get('quantity', 0) != 0:
                    try:
                        if get_kite_connected():
                            kite.place_order(variety="regular", exchange="NFO", tradingsymbol=p['tradingsymbol'], transaction_type="SELL" if p['quantity'] > 0 else "BUY", quantity=abs(p['quantity']), product="MIS", order_type="MARKET")
                            exited.append(p['tradingsymbol'])
                    except:
                        pass
            return {"success": True, "message": f"Exited: {', '.join(exited) or 'None'}"}
        try:
            if get_kite_connected():
                result = kite.place_order(variety="regular", exchange="NFO" if trade["symbol"].endswith(('CE','PE','FUT')) else "NSE", tradingsymbol=trade["symbol"], transaction_type=trade["transaction_type"], quantity=trade["quantity"], product=trade.get("product","MIS"), order_type=trade.get("order_type","MARKET"), price=trade.get("price"))
                log_trade(result, trade["symbol"], trade["transaction_type"], trade["quantity"], trade.get("price"), "PENDING")
                return {"success": True, "message": f"✅ Order placed: {result}"}
            return {"success": False, "message": "Kite not connected"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}
    
    trade_queue[:] = [t for t in trade_queue if t.get("id") != request.queue_id]
    return {"success": True, "message": "Trade rejected"}

@app.post("/api/kill-switch")
async def kill_switch():
    positions = get_positions()
    exited = []
    for p in positions:
        if p.get('quantity', 0) != 0:
            try:
                if get_kite_connected():
                    kite.place_order(variety="regular", exchange="NFO", tradingsymbol=p['tradingsymbol'], transaction_type="SELL" if p['quantity'] > 0 else "BUY", quantity=abs(p['quantity']), product="MIS", order_type="MARKET")
                    exited.append(p['tradingsymbol'])
            except:
                pass
    return {"success": True, "message": f"Kill switch: {', '.join(exited) or 'None'}"}

@app.post("/webhook/signal")
async def receive_signal(data: SignalInput):
    trade_queue.append({"id": len(trade_queue) + 1, "symbol": "PENDING", "transaction_type": "BUY", "quantity": 1, "order_type": "MARKET", "notes": data.message, "source": data.source})
    return {"status": "accepted", "message": "Signal added to queue"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "4444"))
    uvicorn.run(app, host="0.0.0.0", port=port)
