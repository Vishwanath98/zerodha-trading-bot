import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Zerodha Trading Bot", version="2.0.0")

# ============= CONFIG =============
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "false").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

# ============= DATABASE =============
import sqlite3
DB_PATH = os.getenv("DB_PATH", "trading_bot.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT NOT NULL,
            bot_response TEXT NOT NULL,
            trade_action TEXT,
            confirmed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS trade_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    conn.commit()
    conn.close()

init_db()

# ============= KITE CONNECTION =============
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

# ============= IN-MEMORY STATE =============
trade_queue = []
last_positions = []

# ============= MODELS =============
class ChatMessage(BaseModel):
    message: str

class TradeRequest(BaseModel):
    symbol: str
    transaction_type: str
    quantity: int
    product: str = "MIS"
    order_type: str = "MARKET"
    price: float = None

class QueueConfirm(BaseModel):
    queue_id: int
    action: str

# ============= HELPERS =============
def get_positions() -> List[Dict]:
    if not get_kite_connected():
        return last_positions
    
    try:
        pos = kite.positions()
        return pos.get('net', [])
    except:
        return last_positions

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

def log_chat(user_msg: str, bot_msg: str, trade_action: str = None):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_history (user_message, bot_response, trade_action) VALUES (?, ?, ?)",
        (user_msg, bot_msg, trade_action)
    )
    conn.commit()
    conn.close()

def log_trade(order_id: str, symbol: str, transaction_type: str, quantity: int, price: float, status: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO trades (order_id, symbol, transaction_type, quantity, price, status) VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, symbol, transaction_type, quantity, price, status)
    )
    conn.commit()
    conn.close()

def get_trade_metrics() -> Dict:
    conn = get_db()
    
    # Get closed trades
    trades = conn.execute("""
        SELECT * FROM trades 
        WHERE closed_at IS NOT NULL 
        ORDER BY closed_at DESC 
        LIMIT 100
    """).fetchall()
    
    if not trades:
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
    
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    total_pnl = sum(t['pnl'] for t in trades)
    
    return {
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / len(trades) if trades else 0
    }

# ============= SMART CHAT PARSER =============
class SmartChatParser:
    """Understands natural language and cross-checks with positions"""
    
    def __init__(self):
        self.known_symbols = {}  # Will be populated from positions
    
    def update_positions(self, positions: List[Dict]):
        """Build symbol map from current positions"""
        self.known_symbols = {}
        for p in positions:
            symbol = p.get('tradingsymbol', '')
            if symbol:
                # Add various aliases
                self.known_symbols[symbol.lower()] = symbol
                # Add base name (e.g., "sensex" -> "SENSEX2631277000CE")
                base = re.sub(r'\d+', '', symbol.upper())
                if base:
                    self.known_symbols[base.lower()] = symbol
    
    def parse(self, message: str, positions: List[Dict]) -> Dict:
        """Parse message and cross-check with positions"""
        msg = message.lower().strip()
        
        # Check for position queries first
        if 'position' in msg or 'holding' in msg:
            return self._handle_position_query(positions, msg)
        
        if 'pnl' in msg or 'profit' in msg or 'loss' in msg:
            return self._handle_pnl_query(positions)
        
        if 'margin' in msg:
            return {"type": "info", "message": "margin_query"}
        
        if 'buy' in msg or 'sell' in msg:
            return self._handle_trade_request(msg, positions)
        
        if 'exit' in msg or 'close' in msg or 'square' in msg:
            return self._handle_exit_request(msg, positions)
        
        if 'metric' in msg or 'stat' in msg or 'performance' in msg:
            return {"type": "info", "message": "metrics_query"}
        
        return {"type": "info", "message": "general_query"}
    
    def _handle_position_query(self, positions: List[Dict], msg: str) -> Dict:
        if not positions:
            return {
                "type": "response",
                "message": "You have no open positions."
            }
        
        # Check for specific symbol mentions
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        return {
                            "type": "response",
                            "message": f"Your {full_symbol} position:\n"
                                      f"Quantity: {p.get('quantity', 0)}\n"
                                      f"Avg Price: ₹{p.get('average_price', 0)}\n"
                                      f"P&L: ₹{p.get('pnl', 0):.2f}"
                        }
        
        # Show all positions
        text = "📊 Your Open Positions:\n\n"
        for p in positions[:10]:
            symbol = p.get('tradingsymbol', 'N/A')
            qty = p.get('quantity', 0)
            avg = p.get('average_price', 0)
            pnl = p.get('pnl', 0)
            if qty != 0:
                text += f"• {symbol}: {qty} qty @ ₹{avg} | P&L: ₹{pnl:.2f}\n"
        
        return {"type": "response", "message": text}
    
    def _handle_pnl_query(self, positions: List[Dict]) -> Dict:
        total_pnl = sum(p.get('pnl', 0) for p in positions)
        
        wins = sum(1 for p in positions if p.get('pnl', 0) > 0)
        losses = sum(1 for p in positions if p.get('pnl', 0) < 0)
        
        text = f"📈 Today's P&L: ₹{total_pnl:.2f}\n"
        text += f"Winning positions: {wins}\n"
        text += f"Losing positions: {losses}"
        
        return {"type": "response", "message": text}
    
    def _handle_trade_request(self, msg: str, positions: List[Dict]) -> Dict:
        # Determine buy or sell
        is_buy = 'buy' in msg
        transaction_type = "BUY" if is_buy else "SELL"
        
        # Find symbol from positions if mentioned
        symbol = None
        quantity = 1
        price = None
        
        # Check if adding to existing position
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                symbol = full_symbol
                # Find current quantity
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        quantity = abs(p.get('quantity', 0))
                        break
                break
        
        # Extract numbers (strike prices, etc)
        numbers = re.findall(r'\d+', msg)
        if numbers and not symbol:
            # Try to construct symbol - this needs instrument lookup
            return {
                "type": "needs_more",
                "message": f"I found {transaction_type} request but need more details.\n"
                           f"Current message: {message}\n\n"
                           f"Please specify:\n"
                           f"• Full symbol (e.g., NIFTY2631722500CE)\n"
                           f"• Quantity\n"
                           f"• Price (optional, for limit orders)"
            }
        
        if not symbol:
            return {
                "type": "needs_more",
                "message": "Which symbol would you like to trade? Examples:\n"
                           f"• NIFTY 22500 CE\n"
                           f"• BANKNIFTY\n"
                           f"• A stock name"
            }
        
        # Add to queue
        return {
            "type": "trade_request",
            "message": f"{transaction_type} {symbol} x{quantity}",
            "symbol": symbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": "MARKET" if not price else "LIMIT",
            "price": price
        }
    
    def _handle_exit_request(self, msg: str, positions: List[Dict]) -> Dict:
        # Check for specific symbol
        for symbol_key, full_symbol in self.known_symbols.items():
            if symbol_key in msg:
                for p in positions:
                    if p.get('tradingsymbol', '').upper() == full_symbol.upper():
                        qty = p.get('quantity', 0)
                        if qty == 0:
                            return {"type": "response", "message": f"You don't have a position in {full_symbol}."}
                        
                        return {
                            "type": "trade_request",
                            "message": f"Exit {full_symbol} ({qty} qty)?",
                            "symbol": full_symbol,
                            "transaction_type": "SELL" if qty > 0 else "BUY",
                            "quantity": abs(qty),
                            "order_type": "MARKET"
                        }
        
        # Exit all
        if 'all' in msg:
            return {
                "type": "confirm_action",
                "message": "⚠️ This will EXIT ALL positions. Confirm?",
                "action": "exit_all"
            }
        
        return {
            "type": "needs_more",
            "message": "Which position would you like to exit? Specify the symbol or say 'exit all'."
        }

parser = SmartChatParser()

# ============= OLLAMA INTEGRATION =============
def call_ollama(prompt: str) -> Optional[str]:
    """Call local Ollama for smart responses"""
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json().get('response', '').strip()
    except Exception as e:
        print(f"Ollama error: {e}")
    return None

def build_context_for_llm(positions: List[Dict], metrics: Dict) -> str:
    """Build context string for LLM"""
    context = "Current trading session info:\n\n"
    
    context += "OPEN POSITIONS:\n"
    for p in positions:
        qty = p.get('quantity', 0)
        if qty != 0:
            context += f"- {p.get('tradingsymbol')}: {qty} qty @ ₹{p.get('average_price', 0)}, P&L: ₹{p.get('pnl', 0):.2f}\n"
    
    context += f"\nDAILY METRICS:\n"
    context += f"- Total Trades: {metrics.get('total_trades', 0)}\n"
    context += f"- Win Rate: {metrics.get('win_rate', 0)}%\n"
    context += f"- Total P&L: ₹{metrics.get('total_pnl', 0):.2f}\n"
    
    return context

# ============= ROUTES =============

@app.get("/")
async def root():
    return {
        "name": "Zerodha Trading Bot",
        "version": "2.1.0",
        "features": ["Smart Chat", "Position Cross-check", "Trade Queue", "Metrics"],
        "endpoints": ["/", "/api/chat", "/api/queue", "/api/metrics"]
    }

@app.get("/api/stats")
async def get_stats():
    positions = get_positions()
    margins = get_margins()
    
    daily_pnl = sum(p.get('pnl', 0) for p in positions)
    
    return {
        "daily_pnl": daily_pnl,
        "available_margin": margins.get('equity', {}).get('available', {}).get('live_balance', 0),
        "open_positions": len([p for p in positions if p.get('quantity', 0) != 0]),
        "kite_connected": get_kite_connected(),
        "paper_trading": PAPER_TRADING
    }

@app.get("/api/positions")
async def get_positions_api():
    return get_positions()

@app.get("/api/orders")
async def get_orders_api():
    return get_orders()

@app.get("/api/metrics")
async def get_metrics():
    return get_trade_metrics()

@app.get("/api/chat-history")
async def get_chat_history(limit: int = 20):
    conn = get_db()
    chats = conn.execute(
        "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(c) for c in chats]

@app.post("/api/chat")
async def chat(message: ChatMessage):
    msg = message.message.strip()
    
    # Get current positions and update parser
    positions = get_positions()
    parser.update_positions(positions)
    
    # Get metrics
    metrics = get_trade_metrics()
    
    # First try smart parsing
    parsed = parser.parse(msg, positions)
    
    response_text = ""
    trade_request = None
    
    if parsed["type"] == "response":
        response_text = parsed["message"]
    
    elif parsed["type"] == "needs_more":
        # Try Ollama for better understanding
        context = build_context_for_llm(positions, metrics)
        prompt = f"""{context}

User said: "{msg}"

The bot couldn't understand the user's request. Respond helpfully asking for clarification. Keep it short."""

        ollama_response = call_ollama(prompt)
        if ollama_response:
            response_text = ollama_response
        else:
            response_text = parsed["message"]
    
    elif parsed["type"] == "trade_request":
        # Add to queue
        trade_data = {
            "id": len(trade_queue) + 1,
            "symbol": parsed.get("symbol"),
            "transaction_type": parsed.get("transaction_type"),
            "quantity": parsed.get("quantity"),
            "order_type": parsed.get("order_type"),
            "price": parsed.get("price")
        }
        trade_queue.append(trade_data)
        
        response_text = f"📋 Trade added to queue:\n{parsed['message']}\n\nClick CONFIRM to place order."
        trade_request = trade_data
    
    elif parsed["type"] == "confirm_action":
        if parsed.get("action") == "exit_all":
            trade_queue.append({
                "id": len(trade_queue) + 1,
                "action": "exit_all",
                "message": "Exit ALL positions?"
            })
            response_text = "⚠️ Exit ALL positions added to queue for confirmation."
    
    else:
        # Use LLM for general questions
        context = build_context_for_llm(positions, metrics)
        prompt = f"""You are a trading bot assistant. Current session info:
{context}

User asks: "{msg}"

Respond helpfully and concisely. If they want to trade, guide them to specify the symbol, quantity, etc."""

        ollama_response = call_ollama(prompt)
        if ollama_response:
            response_text = ollama_response
        else:
            response_text = "I didn't understand. Try 'show my positions' or 'what's my pnl'."
    
    # Log to database
    log_chat(msg, response_text, json.dumps(trade_request) if trade_request else None)
    
    return {
        "response": response_text,
        "trade_request": trade_request,
        "positions_count": len([p for p in positions if p.get('quantity', 0) != 0])
    }

@app.get("/api/queue")
async def get_queue():
    return trade_queue

@app.post("/api/queue/confirm")
async def confirm_trade(request: QueueConfirm):
    trade = None
    for t in trade_queue:
        if t.get("id") == request.queue_id:
            trade = t
            break
    
    if not trade:
        return {"success": False, "message": "Trade not found"}
    
    if request.action == "confirm":
        # Execute trade
        if trade.get("action") == "exit_all":
            positions = get_positions()
            exited = []
            for p in positions:
                if p.get('quantity', 0) != 0:
                    try:
                        if get_kite_connected():
                            kite.place_order(
                                variety="regular",
                                exchange="NFO",
                                tradingsymbol=p['tradingsymbol'],
                                transaction_type="SELL" if p['quantity'] > 0 else "BUY",
                                quantity=abs(p['quantity']),
                                product="MIS",
                                order_type="MARKET"
                            )
                            exited.append(p['tradingsymbol'])
                    except:
                        pass
            return {"success": True, "message": f"Exited: {', '.join(exited) or 'None'}"}
        
        try:
            if get_kite_connected():
                result = kite.place_order(
                    variety="regular",
                    exchange="NFO" if trade["symbol"].endswith(('CE', 'PE', 'FUT')) else "NSE",
                    tradingsymbol=trade["symbol"],
                    transaction_type=trade["transaction_type"],
                    quantity=trade["quantity"],
                    product=trade.get("product", "MIS"),
                    order_type=trade.get("order_type", "MARKET"),
                    price=trade.get("price")
                )
                log_trade(result, trade["symbol"], trade["transaction_type"], 
                         trade["quantity"], trade.get("price"), "PENDING")
                return {"success": True, "message": f"✅ Order placed: {result}"}
            else:
                return {"success": False, "message": "Kite not connected"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}
    
    # Remove from queue
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
                    kite.place_order(
                        variety="regular",
                        exchange="NFO",
                        tradingsymbol=p['tradingsymbol'],
                        transaction_type="SELL" if p['quantity'] > 0 else "BUY",
                        quantity=abs(p['quantity']),
                        product="MIS",
                        order_type="MARKET"
                    )
                    exited.append(p['tradingsymbol'])
            except:
                pass
    
    return {"success": True, "message": f"Kill switch executed. Exited: {', '.join(exited) or 'None'}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "4444"))
    uvicorn.run(app, host="0.0.0.0", port=port)
