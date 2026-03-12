import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Zerodha Trading Bot", version="2.0.0")

# ============= STATE =============
KITE_API_KEY = os.getenv("KITE_API_KEY", "3v3h2zkvyqhn163b")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "false").lower() == "true"

# In-memory databases
signals_db = []
positions_db = []
trade_queue = []  # Pending trades waiting for confirmation
chat_history = []
order_history = []

# Kite connection
kite = None
if KITE_ACCESS_TOKEN:
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=KITE_API_KEY)
        kite.set_access_token(KITE_ACCESS_TOKEN)
    except:
        pass

# ============= MODELS =============
class SignalInput(BaseModel):
    message: str = ""
    source: str = "webhook"

class TradeRequest(BaseModel):
    symbol: str
    transaction_type: str
    quantity: int
    product: str = "MIS"
    order_type: str = "MARKET"
    price: float = None
    stop_loss: float = None
    target: float = None
    notes: str = ""

class QueueConfirmRequest(BaseModel):
    queue_id: int
    action: str  # "confirm" or "reject"

class ChatMessage(BaseModel):
    message: str

# ============= HELPERS =============
def get_kite_connected():
    return kite is not None and bool(KITE_ACCESS_TOKEN)

def get_positions():
    if not get_kite_connected():
        return positions_db
    
    try:
        pos = kite.positions()
        return pos.get('net', [])
    except:
        return positions_db

def get_margins():
    if PAPER_TRADING:
        return {"equity": {"net": 100000, "available": 100000}}
    
    if not get_kite_connected():
        return {"error": "Not connected"}
    
    try:
        return kite.margins()
    except:
        return {"error": "Failed to get margins"}

def get_orders():
    if not get_kite_connected():
        return order_history
    
    try:
        return kite.orders()
    except:
        return []

# ============= ROUTES =============

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return '''<!DOCTYPE html>
<html>
<head>
    <title>Zerodha Trading Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        /* Header */
        .header { display: flex; justify-content: space-between; align-items: center; padding: 20px; background: #161b22; border-radius: 12px; margin-bottom: 20px; }
        .logo { font-size: 24px; font-weight: bold; color: #58a6ff; }
        .status { display: flex; gap: 20px; align-items: center; }
        .badge { padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .badge.green { background: #238636; color: white; }
        .badge.red { background: #da3633; color: white; }
        
        /* Kill Switch */
        .kill-switch { background: #da3633; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 14px; }
        .kill-switch:hover { background: #f85149; }
        
        /* Grid */
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        
        /* Cards */
        .card { background: #161b22; border-radius: 12px; padding: 20px; }
        .card h2 { font-size: 16px; color: #8b949e; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        
        /* Stats */
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
        .stat-box { background: #161b22; padding: 20px; border-radius: 12px; text-align: center; }
        .stat-value { font-size: 28px; font-weight: bold; }
        .stat-label { font-size: 12px; color: #8b949e; margin-top: 4px; }
        .profit { color: #3fb950; }
        .loss { color: #f85149; }
        
        /* Chat */
        .chat-container { height: 400px; display: flex; flex-direction: column; }
        .chat-messages { flex: 1; overflow-y: auto; padding: 16px; background: #0d1117; border-radius: 8px; margin-bottom: 16px; }
        .message { margin-bottom: 12px; padding: 12px 16px; border-radius: 12px; max-width: 80%; }
        .message.user { background: #1f6feb; color: white; margin-left: auto; }
        .message.bot { background: #21262d; }
        .chat-input { display: flex; gap: 8px; }
        .chat-input input { flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: white; font-size: 14px; }
        .chat-input button { padding: 12px 24px; background: #238636; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
        
        /* Trade Queue */
        .queue-item { background: #0d1117; padding: 16px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #f0883e; }
        .queue-item-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .queue-symbol { font-weight: bold; color: #58a6ff; }
        .queue-type { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        .queue-type.buy { background: #238636; }
        .queue-type.sell { background: #da3633; }
        .queue-details { font-size: 14px; color: #8b949e; }
        .queue-actions { display: flex; gap: 8px; margin-top: 12px; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
        .btn-confirm { background: #238636; color: white; }
        .btn-reject { background: #30363d; color: white; }
        
        /* Orders */
        .orders-list { max-height: 300px; overflow-y: auto; }
        .order-item { display: flex; justify-content: space-between; padding: 12px; border-bottom: 1px solid #21262d; }
        .order-status.complete { color: #3fb950; }
        .order-status.rejected { color: #f85149; }
        
        /* Position Table */
        .positions-table { width: 100%; border-collapse: collapse; }
        .positions-table th { text-align: left; padding: 12px; color: #8b949e; font-size: 12px; border-bottom: 1px solid #21262d; }
        .positions-table td { padding: 12px; border-bottom: 1px solid #21262d; }
        
        /* Quick Actions */
        .quick-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .quick-btn { padding: 8px 16px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; cursor: pointer; font-size: 13px; }
        .quick-btn:hover { background: #30363d; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo">🤖 Trading Bot</div>
            <div class="status">
                <span class="badge green" id="connectionStatus">Connected</span>
                <span class="badge" id="paperStatus">PAPER MODE</span>
                <button class="kill-switch" onclick="killSwitch()">🔴 KILL SWITCH</button>
            </div>
        </div>
        
        <!-- Stats -->
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value" id="pnlValue">₹0</div>
                <div class="stat-label">Today's P&L</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="marginValue">₹0</div>
                <div class="stat-label">Available Margin</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="positionCount">0</div>
                <div class="stat-label">Open Positions</div>
            </div>
        </div>
        
        <div class="grid">
            <!-- Chat -->
            <div class="card">
                <h2>💬 Command Center</h2>
                <div class="chat-container">
                    <div class="chat-messages" id="chatMessages">
                        <div class="message bot">Hello! I'm your trading assistant. Give me commands like:<br><br>
                        • "Buy 1 lot NIFTY at market"<br>
                        • "Show my positions"<br>
                        • "What's my P&L?"<br>
                        • "Exit all positions"<br><br>
                        I'll ask for confirmation before placing any trade!</div>
                    </div>
                    <div class="chat-input">
                        <input type="text" id="chatInput" placeholder="Type your command..." onkeypress="if(event.key==='Enter')sendMessage()">
                        <button onclick="sendMessage()">Send</button>
                    </div>
                </div>
            </div>
            
            <!-- Trade Queue -->
            <div class="card">
                <h2>📋 Trade Queue (Awaiting Confirmation)</h2>
                <div id="tradeQueue">
                    <p style="color: #8b949e;">No trades pending confirmation.</p>
                </div>
            </div>
        </div>
        
        <!-- Positions -->
        <div class="card" style="margin-top: 20px;">
            <h2>📊 Open Positions</h2>
            <div id="positionsTable">
                <p style="color: #8b949e;">No open positions</p>
            </div>
        </div>
        
        <!-- Recent Orders -->
        <div class="card" style="margin-top: 20px;">
            <h2>📜 Recent Orders</h2>
            <div class="orders-list" id="ordersList"></div>
        </div>
    </div>
    
    <script>
        let pendingTrades = [];
        
        // Send chat message
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            addMessage(message, 'user');
            input.value = '';
            
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message})
            });
            const data = await response.json();
            
            if (data.response) {
                addMessage(data.response, 'bot');
            }
            
            if (data.trade_request) {
                addTradeToQueue(data.trade_request);
            }
            
            refreshData();
        }
        
        function addMessage(text, sender) {
            const container = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = 'message ' + sender;
            div.innerHTML = text;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }
        
        function addTradeToQueue(trade) {
            trade.id = Date.now();
            pendingTrades.push(trade);
            renderQueue();
        }
        
        function renderQueue() {
            const container = document.getElementById('tradeQueue');
            if (pendingTrades.length === 0) {
                container.innerHTML = '<p style="color: #8b949e;">No trades pending confirmation.</p>';
                return;
            }
            
            container.innerHTML = pendingTrades.map(t => `
                <div class="queue-item">
                    <div class="queue-item-header">
                        <span class="queue-symbol">${t.symbol}</span>
                        <span class="queue-type ${t.transaction_type.toLowerCase()}">${t.transaction_type}</span>
                    </div>
                    <div class="queue-details">
                        Qty: ${t.quantity} | Price: ${t.order_type} ${t.price ? '@ ₹'+t.price : 'Market'}
                        ${t.stop_loss ? '<br>SL: ₹'+t.stop_loss : ''}
                        ${t.target ? '<br>TARGET: ₹'+t.target : ''}
                    </div>
                    <div class="queue-actions">
                        <button class="btn btn-confirm" onclick="confirmTrade(${t.id})">✓ CONFIRM</button>
                        <button class="btn btn-reject" onclick="rejectTrade(${t.id})">✗ REJECT</button>
                    </div>
                </div>
            `).join('');
        }
        
        async function confirmTrade(id) {
            const trade = pendingTrades.find(t => t.id === id);
            if (!trade) return;
            
            const response = await fetch('/api/queue/confirm', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({queue_id: id, action: 'confirm'})
            });
            const data = await response.json();
            
            pendingTrades = pendingTrades.filter(t => t.id !== id);
            renderQueue();
            addMessage(data.message, 'bot');
            refreshData();
        }
        
        async function rejectTrade(id) {
            pendingTrades = pendingTrades.filter(t => t.id !== id);
            renderQueue();
            addMessage('Trade rejected.', 'bot');
        }
        
        async function killSwitch() {
            if (!confirm('⚠️ KILL SWITCH: This will exit ALL positions. Continue?')) return;
            
            const response = await fetch('/api/kill-switch', {method: 'POST'});
            const data = await response.json();
            addMessage(data.message, 'bot');
            refreshData();
        }
        
        async function refreshData() {
            // Get stats
            const statsRes = await fetch('/api/stats');
            const stats = await statsRes.json();
            
            const pnlEl = document.getElementById('pnlValue');
            pnlEl.textContent = '₹' + (stats.daily_pnl || 0).toFixed(0);
            pnlEl.className = 'stat-value ' + (stats.daily_pnl >= 0 ? 'profit' : 'loss');
            
            document.getElementById('marginValue').textContent = '₹' + (stats.available_margin || 0).toFixed(0);
            document.getElementById('positionCount').textContent = stats.open_positions || 0;
            
            // Get positions
            const posRes = await fetch('/api/positions');
            const positions = await posRes.json();
            
            if (positions.length > 0) {
                document.getElementById('positionsTable').innerHTML = `
                    <table class="positions-table">
                        <tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th><th>Action</th></tr>
                        ${positions.slice(0,10).map(p => `
                            <tr>
                                <td>${p.tradingsymbol || p.symbol}</td>
                                <td>${p.quantity}</td>
                                <td>₹${p.average_price || p.entry_price || 0}</td>
                                <td>₹${p.last_price || 0}</td>
                                <td class="${(p.pnl || 0) >= 0 ? 'profit' : 'loss'}">₹${p.pnl || 0}</td>
                                <td><button class="btn btn-reject" onclick="exitPosition('${p.tradingsymbol || p.symbol}', ${p.quantity})">Exit</button></td>
                            </tr>
                        `).join('')}
                    </table>
                `;
            }
            
            // Get orders
            const ordersRes = await fetch('/api/orders');
            const orders = await ordersRes.json();
            
            if (orders.length > 0) {
                document.getElementById('ordersList').innerHTML = orders.slice(0,5).map(o => `
                    <div class="order-item">
                        <span>${o.tradingsymbol} ${o.transaction_type} x${o.filled_quantity}</span>
                        <span class="order-status ${o.status.toLowerCase()}">${o.status}</span>
                    </div>
                `).join('');
            }
        }
        
        async function exitPosition(symbol, qty) {
            if (!confirm(`Exit ${symbol} (${qty} qty)?`)) return;
            
            const response = await fetch('/api/orders/place', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    symbol: symbol,
                    transaction_type: qty > 0 ? 'SELL' : 'BUY',
                    quantity: Math.abs(qty),
                    product: 'MIS'
                })
            });
            const data = await response.json();
            addMessage(data.order_id ? `Exit order placed: ${data.order_id}` : data.detail || 'Error', 'bot');
            refreshData();
        }
        
        // Refresh every 10 seconds
        refreshData();
        setInterval(refreshData, 10000);
    </script>
</body>
</html>'''

# ============= API ENDPOINTS =============

@app.get("/api/stats")
async def get_stats():
    positions = get_positions()
    margins = get_margins()
    orders = get_orders()
    
    # Calculate P&L
    daily_pnl = 0
    for p in positions:
        daily_pnl += p.get('pnl', 0)
    
    return {
        "daily_pnl": daily_pnl,
        "available_margin": margins.get('equity', {}).get('available', {}).get('live_balance', 0) if isinstance(margins, dict) else 0,
        "open_positions": len([p for p in positions if p.get('quantity', 0) != 0]),
        "total_orders": len(orders),
        "paper_trading": PAPER_TRADING,
        "kite_connected": get_kite_connected()
    }

@app.get("/api/positions")
async def get_positions_api():
    return get_positions()

@app.get("/api/orders")
async def get_orders_api():
    return get_orders()

@app.get("/api/margins")
async def get_margins_api():
    return get_margins()

@app.post("/api/chat")
async def chat(message: ChatMessage):
    msg = message.message.lower().strip()
    
    # Parse commands
    if 'position' in msg or 'show' in msg and 'position' in msg:
        positions = get_positions()
        if not positions:
            return {"response": "No open positions."}
        
        text = "📊 Your Positions:\n\n"
        for p in positions[:5]:
            symbol = p.get('tradingsymbol', 'N/A')
            qty = p.get('quantity', 0)
            avg = p.get('average_price', 0)
            pnl = p.get('pnl', 0)
            text += f"• {symbol}: {qty} qty @ ₹{avg} | P&L: ₹{pnl:.2f}\n"
        
        return {"response": text}
    
    if 'pnl' in msg or 'profit' in msg or 'loss' in msg:
        positions = get_positions()
        total_pnl = sum(p.get('pnl', 0) for p in positions)
        return {"response": f"Today's P&L: ₹{total_pnl:.2f}"}
    
    if 'margin' in msg:
        margins = get_margins()
        avail = margins.get('equity', {}).get('available', {}).get('live_balance', 0)
        return {"response": f"Available margin: ₹{avail:.2f}"}
    
    if 'exit' in msg and 'position' in msg or 'close' in msg:
        # Add kill switch to queue
        return {"response": "⚠️ This will exit ALL positions. Type 'yes, kill all' to confirm.", "trade_request": {"action": "kill_switch"}}
    
    if msg == 'yes, kill all':
        positions = get_positions()
        return {"response": "Processing kill switch...", "action": "kill_switch"}
    
    # Trade parsing
    if 'buy' in msg or 'sell' in msg:
        # Simple parsing - in production use NLP
        return {
            "response": "I need more details. Please specify:\n• Symbol (e.g., NIFTY, BANKNIFTY)\n• Strike price (for options)\n• CE or PE\n• Quantity\n\nExample: 'Buy 1 lot NIFTY 22500 CE'",
            "trade_request": {
                "symbol": "PENDING_PARSE",
                "transaction_type": "BUY" if "buy" in msg else "SELL",
                "quantity": 1,
                "order_type": "MARKET",
                "notes": msg
            }
        }
    
    return {"response": "I didn't understand. Try:\n• 'Show my positions'\n• 'What's my P&L?'\n• 'Buy NIFTY 22500 CE'"}

@app.post("/api/queue/confirm")
async def confirm_trade(request: QueueConfirmRequest):
    trade = None
    for t in trade_queue:
        if t.get('id') == request.queue_id:
            trade = t
            break
    
    if not trade:
        return {"message": "Trade not found", "success": False}
    
    if request.action == "confirm":
        try:
            order_params = {
                "symbol": trade["symbol"],
                "transaction_type": trade["transaction_type"],
                "quantity": trade["quantity"],
                "product": trade.get("product", "MIS"),
                "order_type": trade.get("order_type", "MARKET"),
                "price": trade.get("price"),
                "stop_loss": trade.get("stop_loss"),
                "target": trade.get("target")
            }
            
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
                return {"message": f"✅ Order placed! Order ID: {result}", "success": True}
            else:
                return {"message": "Kite not connected", "success": False}
                
        except Exception as e:
            return {"message": f"Error: {str(e)}", "success": False}
    else:
        return {"message": "Trade rejected", "success": True}

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
    
    return {"message": f"Kill switch executed. Exited: {', '.join(exited) or 'None'}", "success": True}

@app.post("/api/orders/place")
async def place_order(order: TradeRequest):
    # Always add to queue first for confirmation
    trade = {
        "id": len(trade_queue) + 1,
        "symbol": order.symbol,
        "transaction_type": order.transaction_type,
        "quantity": order.quantity,
        "product": order.product,
        "order_type": order.order_type,
        "price": order.price,
        "stop_loss": order.stop_loss,
        "target": order.target,
        "notes": order.notes
    }
    trade_queue.append(trade)
    
    return {
        "message": f"Trade added to queue for confirmation: {order.symbol} {order.transaction_type} x{order.quantity}",
        "queue_id": trade["id"],
        "queued": True
    }

# Webhook for signals
@app.post("/webhook/signal")
async def receive_signal(data: SignalInput):
    signal = {
        "id": len(signals_db) + 1,
        "source": data.source,
        "raw_message": data.message,
        "status": "pending_review",
        "created_at": datetime.now().isoformat()
    }
    signals_db.append(signal)
    
    # Auto-add to trade queue for review
    trade_queue.append({
        "id": len(trade_queue) + 1,
        "symbol": "PENDING_PARSE",
        "transaction_type": "BUY",
        "quantity": 1,
        "order_type": "MARKET",
        "notes": f"Signal: {data.message}"
    })
    
    return {"status": "accepted", "message": "Signal received - added to queue for review"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "4444"))
    uvicorn.run(app, host="0.0.0.0", port=port)
