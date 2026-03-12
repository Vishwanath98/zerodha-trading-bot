# Zerodha Trading Bot - System Specification

## Project Overview
- **Project Name**: Zerodha Trading Bot (Signal-to-Execution System)
- **Type**: Automated Trading System
- **Core Functionality**: Ingest trading signals from multiple sources, validate through technical analysis filters, manage risk, and execute trades on Zerodha Kite
- **Target Users**: Retail traders using Zerodha for NSE options/derivatives

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIGNAL SOURCE ADAPTERS                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │   Telegram   │  │   Channel    │  │    Relay     │  │  Manual/Webhook│ │
│  │    Bot       │  │   Scraper    │  │   Adapter    │  │    Adapter     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAW SIGNAL INBOX                                    │
│                    PostgreSQL + Redis Queue                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PROCESSING PIPELINE                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │ Hinglish Parser │─▶│ Instrument       │─▶│ Market Context Service    │ │
│  │ normalize/extract│  │ Resolver         │  │ candles/spot/LTP/OI/VIX   │ │
│  └─────────────────┘  └──────────────────┘  └────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │Strategy Filter │─▶│   Risk Engine    │─▶│   Research Validation      │ │
│  │OB/Fib/EMA/etc  │  │ size/loss/spread │  │   Agent Research Import    │ │
│  └─────────────────┘  └──────────────────┘  └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION LAYER                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │  Zerodha        │  │   Position       │  │   Trade Monitor            │ │
│  │  Executor       │  │   Manager        │  │   SL/Exit/Sync            │ │
│  └─────────────────┘  └──────────────────┘  └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MONITORING & AUDIT                                     │
│              Dashboard + Alerts + Audit Log                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technical Stack
- **Language**: Python 3.11+
- **Database**: PostgreSQL (signals, positions, audit)
- **Cache/Queue**: Redis (real-time queue, caching)
- **Trading API**: Zerodha Kite Connect API
- **Telegram**: Telethon (user client) / pyrogram
- **Technical Analysis**: pandas-ta, finta
- **Web Framework**: FastAPI (dashboard, webhooks)
- **Task Queue**: Celery + Redis
- **Containerization**: Docker + Docker Compose

## Component Specifications

### 1. Signal Source Adapters

#### 1.1 Telegram Bot Adapter
- Requires bot token from @BotFather
- Limitations: Cannot see other bot messages, needs admin for groups
- Alternative: Use Telethon with user session for full access

#### 1.2 Telegram Channel Scraper (Telethon)
- Uses user authentication (phone number)
- Can read from public channels/groups
- Handles mixed Hinglish content
- Session persistence

#### 1.3 Relay Adapter
- Acts as middleware for signal forwarding
- Accepts signals from other systems

#### 1.4 Manual/Webhook Adapter
- REST API endpoints for manual signal entry
- CSV upload capability
- Webhook接收其他代理的研究结果

### 2. Hinglish Signal Parser
- Input: Raw Hinglish text (e.g., "NIFTY 22500 CE LELO 22550 SL")
- Processing:
  - Language normalization
  - Entity extraction (strike, expiry, CE/PE, entry price)
  - Confidence scoring
- Output: Structured signal dict

### 3. Instrument Resolver
- Maps trading symbols to Zerodha instrument tokens
- Handles:
  - NIFTY/BN/FINNIFTY expiry mapping
  - Strike price mapping
  - CE/PE (Call/Put) mapping
  - Weekly/monthly expiry resolution

### 4. Market Context Service
- Fetches:
  - Candlestick data (1m, 5m, 15m, 1h, 1d)
  - Spot prices
  - Option LTP (last traded price)
  - Open Interest (OI) data
  - VIX levels
- Caches data in Redis with TTL

### 5. Strategy Filter Engine
Technical indicators and patterns:
- **Order Block Detection**: Identifies institutional buying/selling zones
- **Fibonacci Retracement**: Key support/resistance levels
- **EMA Crossover**: 9/21/50/200 EMA combinations
- **Candlestick Patterns**: Doji, hammer, engulfing, etc.
- **Trendline Analysis**: Break/retest validation
- **Volume Analysis**: Unusual volume detection

Each filter returns: pass/fail + confidence score

### 6. Risk Engine
- **Position Sizing**: Based on account balance and risk %
- **Max Loss Protection**: Daily/weekly loss limits
- **Stale Signal Detection**: Time-based filtering
- **Spread Check**: Ensure reasonable bid-ask spread
- **Slippage Estimation**: Based on liquidity

### 7. Research Validation Module
- Import research/calls from external agents
- Validate against own filters
- Confidence scoring for combined validation
- Source attribution for audit

### 8. Zerodha Executor
- Order placement (MIS/NRML)
- Order confirmation tracking
- Stop-loss placement
- Target/exit management
- Position sync on startup

### 9. Position Manager
- Track all open positions
- Monitor P&L in real-time
- Auto-exit on SL hit
- Partial profit booking
- End-of-day square-off

### 10. Dashboard & Monitoring
- **FastAPI Web UI**: Real-time dashboard
- **Telegram Alerts**: Trade execution, errors, daily summary
- **Audit Log**: All actions with timestamps

## Database Schema

### signals table
- id, source, raw_message, parsed_signal, confidence, status, created_at, processed_at

### positions table
- id, instrument_token, symbol, quantity, entry_price, current_price, pnl, stop_loss, target, status, opened_at, closed_at

### orders table
- id, order_id, exchange_order_id, instrument_token, type, quantity, price, status, created_at, filled_at

### audit_logs table
- id, action, details, created_at

### research_calls table
- id, source, content, parsed_data, confidence, validated, created_at

## API Endpoints

### Webhook & Manual
- POST /api/signals - Receive signal
- POST /api/signals/csv - Upload CSV
- POST /api/webhooks/research - Receive external research

### Status & Control
- GET /api/positions - Current positions
- GET /api/orders - Order history
- POST /api/orders/exit/{position_id} - Manual exit
- GET /api/health - Health check
- GET /api/stats - Trading statistics

### Configuration
- GET/PUT /api/config/risk - Risk parameters
- GET/PUT /api/config/filters - Filter settings

## Environment Variables Required

```
# Zerodha
KITE_API_KEY=
KITE_API_SECRET=
KITE_REQUEST_TOKEN=

# Telegram
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELETHON_SESSION_STRING=
TELEGRAM_CHANNEL_ID=

# Database
POSTGRES_HOST=
POSTGRES_PORT=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=

# Redis
REDIS_HOST=
REDIS_PORT=
REDIS_PASSWORD=

# App
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## Deployment

### Docker Compose Services
1. **postgres** - Database
2. **redis** - Cache & Queue
3. **app** - Main application
4. **celery** - Background tasks
5. **celery-beat** - Scheduled tasks

## Testing Strategy
- Unit tests for parser, filters, risk engine
- Integration tests for API endpoints
- Mock Zerodha API for execution tests
- Paper trading mode for live testing
