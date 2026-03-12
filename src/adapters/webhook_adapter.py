from typing import Callable
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from src.core.logger import logger

router = APIRouter()

signal_callback: Callable = None


def set_signal_callback(callback: Callable):
    global signal_callback
    signal_callback = callback


class SignalInput(BaseModel):
    underlying: str
    strike: Optional[int] = None
    option_type: Optional[str] = None
    action: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    quantity: Optional[int] = None


class WebhookInput(BaseModel):
    message: str
    source: str = "webhook"
    timestamp: Optional[datetime] = None


@router.post("/signal")
async def receive_signal(signal: SignalInput):
    """Receive structured signal via webhook."""
    if not signal_callback:
        raise HTTPException(status_code=500, detail="Signal processor not initialized")
    
    try:
        message = f"{signal.underlying} {signal.strike or ''} {signal.option_type or ''} {signal.action}"
        if signal.entry_price:
            message += f" {signal.entry_price}"
        if signal.stop_loss:
            message += f" SL {signal.stop_loss}"
        if signal.target:
            message += f" TARGET {signal.target}"
        
        await signal_callback(signal.source, message)
        return {"status": "accepted", "message": "Signal queued for processing"}
    
    except Exception as e:
        logger.error(f"Error processing webhook signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def receive_webhook(webhook: WebhookInput):
    """Receive raw signal via webhook."""
    if not signal_callback:
        raise HTTPException(status_code=500, detail="Signal processor not initialized")
    
    try:
        await signal_callback(webhook.source, webhook.message)
        return {"status": "accepted", "message": "Webhook signal queued"}
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research")
async def receive_research(data: dict):
    """Receive research/call from external agent."""
    from src.models.models import ResearchCall
    from src.api.deps import get_db
    
    async for db in get_db():
        research = ResearchCall(
            source=data.get('source', 'external_agent'),
            content=data.get('content', ''),
            parsed_data=data.get('parsed_data'),
            confidence=data.get('confidence', 0.0)
        )
        db.add(research)
        await db.commit()
        await db.refresh(research)
        
        logger.info(f"Research call received from {research.source}")
        
        return {
            "status": "accepted",
            "research_id": research.id,
            "message": "Research queued for validation"
        }


from typing import Optional
