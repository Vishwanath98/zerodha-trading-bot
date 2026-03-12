import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Zerodha Trading Bot", version="1.0.0")

@app.get("/")
def root():
    return {
        "name": "Zerodha Trading Bot",
        "version": "1.0.0", 
        "status": "running",
        "endpoints": [
            "/webhook/signal",
            "/webhook/research",
            "/api/positions",
            "/api/signals",
            "/api/stats"
        ]
    }

@app.get("/api/health")
def health():
    return {"status": "healthy"}

# In-memory storage (replace with database later)
signals_db = []
positions_db = []
research_db = []

@app.post("/webhook/signal")
async def receive_signal(data: dict):
    """Receive signal via webhook."""
    message = data.get("message", "")
    source = data.get("source", "webhook")
    
    signal = {
        "id": len(signals_db) + 1,
        "source": source,
        "raw_message": message,
        "status": "pending"
    }
    signals_db.append(signal)
    
    return {"status": "accepted", "signal_id": signal["id"]}

@app.post("/webhook/research")
async def receive_research(data: dict):
    """Receive research from external agents."""
    research = {
        "id": len(research_db) + 1,
        "source": data.get("source", "external"),
        "content": data.get("content", ""),
        "validated": False
    }
    research_db.append(research)
    return {"status": "accepted", "research_id": research["id"]}

@app.get("/api/signals")
def list_signals():
    return signals_db

@app.get("/api/positions")
def list_positions():
    return positions_db

@app.get("/api/stats")
def get_stats():
    return {
        "total_signals": len(signals_db),
        "total_positions": len(positions_db),
        "total_research": len(research_db)
    }

@app.post("/api/positions/exit/{position_id}")
def exit_position(position_id: int, data: dict):
    return {"status": "success", "position_id": position_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "4444"))
    uvicorn.run(app, host="0.0.0.0", port=port)
