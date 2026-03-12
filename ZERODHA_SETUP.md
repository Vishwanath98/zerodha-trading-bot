# Zerodha Kite API Setup Guide

## Step-by-Step Instructions

### 1. Create Kite App

1. **Login to Zerodha Console**
   - Go to: https://kite.zerodha.com/connect/login
   - Login with your Zerodha credentials

2. **Go to Apps Section**
   - After login, go to: https://developers.zerodha.com/
   - Or click your profile → Settings → API Keys
   - Or directly go to: https://kite.zerodha.com/connect/apps

3. **Create New App**
   - Click "Create New App" button
   - Fill form:
     - **App Name**: TradingBot
     - **App URL**: http://localhost:8000 (or your domain)
     - **Redirect URL**: http://localhost:8000/auth (optional)
     - **Permissions**: Select all needed permissions

4. **Get Credentials**
   - After creating, you'll see:
     - `API Key` (like "abcd1234efgh5678")
     - `API Secret` (like "abcdefghijklmnop")

---

### 2. Generate Access Token

After creating the app, you need to generate an access token:

**Option A: Using Kite Console (Easiest)**
1. Go to: https://kite.zerodha.com/connect/apps
2. Click on your app
3. Click "Generate Access Token"
4. It will show a token you can copy

**Option B: Manual OAuth Flow (For Production)**

The full flow requires:
1. Generate request token from: 
   `https://kite.zerodha.com/connect/login?api_key=YOUR_API_KEY&redirect_type=login`
2. Get the request token from the redirect URL
3. Exchange for access token using API

---

### 3. Add to .env File

```
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_ACCESS_TOKEN=your_access_token_here
```

---

### Important Notes

- **Paper Trading**: The system runs in paper trading mode by default. Set `PAPER_TRADING=false` in `.env` to enable real trading.
- **API Limits**: Zerodha has rate limits. The system handles this.
- **Market Hours**: API only works during market hours (9:15 AM - 3:30 PM IST)

---

### Troubleshooting

**Q: Can't see "Apps" option in Kite**
- Make sure you're logged into Kite properly
- Try: https://kite.zerodha.com/connect/apps

**Q: Getting "Invalid API key"**
- Check your API key is correct
- Make sure app is "Published" or in "Sandbox" mode

**Q: Access token expired**
- Access tokens expire periodically
- Re-generate from console or implement token refresh
