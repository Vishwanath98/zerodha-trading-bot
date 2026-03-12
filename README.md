# Zerodha Trading Bot
Automated trading bot with AI-powered chat interface for executing trades on Zerodha Kite.

## Features

- 🤖 **AI Chat Interface** - Natural language commands to place trades
- 📊 **Real-time Dashboard** - Live P&L, positions, and order tracking
- 🔒 **Kill Switch** - Emergency stop for all positions
- ✅ **Confirmation Queue** - All trades require manual approval
- 🧠 **Local LLM Integration** - Uses Ollama for intelligent responses
- 📈 **Trade Analytics** - Win rate, P&L metrics, performance tracking
- 🐳 **Docker Ready** - Easy deployment with Docker Compose

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Browser)                   │
│         Chat UI + Dashboard + Trade Queue              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Smart Chat  │  │ Position     │  │ Trade Queue  │  │
│  │ Parser      │  │ Manager      │  │ Manager      │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Zerodha  │   │ PostgreSQL│   │ Ollama   │
    │ Kite API │   │ Database  │   │ (LLM)    │
    └──────────┘   └──────────┘   └──────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (optional, SQLite for dev)
- Docker & Docker Compose (for deployment)
- Ollama (optional, for AI features)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/zerodha-trading-bot.git
cd zerodha-trading-bot
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Edit `.env` with your credentials:
```env
# Zerodha API (get from https://developers.kite.trade)
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_ACCESS_TOKEN=your_access_token

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=tradingbot
POSTGRES_PASSWORD=your_password
POSTGRES_DB=tradingbot

# Ollama (optional, for AI features)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b

# App Settings
PAPER_TRADING=false
PORT=4444
```

4. Run with Docker:
```bash
docker-compose up -d
```

Or run directly:
```bash
pip install -r requirements.txt
python src/api/main.py
```

5. Open browser: http://localhost:4444

## Usage

### Chat Commands

- "Show my positions" - View open positions
- "What's my P&L?" - Check profit/loss
- "Buy NIFTY 22500 CE" - Place buy order
- "Exit SENSEX" - Close position
- "Kill switch" - Close all positions

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/chat` | POST | Send chat message |
| `/api/positions` | GET | Get positions |
| `/api/orders` | GET | Get order history |
| `/api/metrics` | GET | Trading metrics |
| `/api/queue` | GET | Trade queue |
| `/api/queue/confirm` | POST | Confirm trade |
| `/api/kill-switch` | POST | Exit all positions |
| `/webhook/signal` | POST | Receive signals |

## Webhook Usage

Send signals via webhook:
```bash
curl -X POST http://localhost:4444/webhook/signal \
  -H "Content-Type: application/json" \
  -d '{"message": "NIFTY 22500 CE BUY", "source": "telegram"}'
```

## Trading Metrics

The bot tracks:
- Win rate
- Profit factor
- Average P&L per trade
- Maximum drawdown
- Trade frequency

## Development

### Project Structure

```
├── src/
│   ├── api/              # FastAPI endpoints
│   ├── services/         # Business logic
│   ├── models/           # Database models
│   └── utils/            # Utilities
├── tests/                # Unit tests
├── docker-compose.yml    # Docker orchestration
├── Dockerfile           # App container
└── requirements.txt    # Python dependencies
```

### Running Tests

```bash
pytest tests/
```

## Security Notes

- ⚠️ **Paper Trading**: Always test with `PAPER_TRADING=true` first
- ⚠️ **SEBI Compliance**: Ensure static IP registration for algo trading
- ⚠️ **API Keys**: Never commit credentials to version control
- ⚠️ **Kill Switch**: Test the emergency exit before live trading

## License

MIT License

## Disclaimer

This software is for educational purposes. Use at your own risk. Always understand the risks of algorithmic trading.
