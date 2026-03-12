from celery import Celery
from src.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tradingbot",
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)


@celery_app.task
def sync_positions():
    """Sync positions with Zerodha."""
    from src.models.models import async_session
    from src.services.position_manager import PositionMonitor
    import asyncio
    
    async def _sync():
        async with async_session() as db:
            monitor = PositionMonitor(db)
            await monitor.run_checks()
    
    asyncio.run(_sync())


@celery_app.task
def update_market_data():
    """Update market data for all open positions."""
    from src.models.models import async_session, select, Position
    from src.services.executor import executor
    import asyncio
    
    async def _update():
        async with async_session() as db:
            result = await db.execute(
                select(Position).where(Position.status == 'open')
            )
            positions = result.scalars().all()
            
            for pos in positions:
                quote = executor.get_quote(pos.symbol)
                if quote:
                    pos.current_price = quote.get('last_price')
                    pos.pnl = (pos.current_price - pos.entry_price) * pos.quantity
            
            await db.commit()
    
    asyncio.run(_update())


@celery_app.task
def send_daily_summary():
    """Send daily trading summary."""
    from src.models.models import async_session, select, Position
    import asyncio
    from datetime import datetime, timedelta
    
    async def _send():
        async with async_session() as db:
            today = datetime.utcnow().date()
            result = await db.execute(
                select(Position).where(Position.closed_at >= today)
            )
            positions = result.scalars().all()
            
            total_pnl = sum(p.pnl for p in positions)
            
            print(f"Daily Summary: {len(positions)} trades, PnL: {total_pnl}")
    
    asyncio.run(_send())


@celery_app.task
def validate_pending_research():
    """Validate pending research calls."""
    from src.models.models import async_session, select, ResearchCall
    from src.services.signal_processor import ResearchValidator
    import asyncio
    
    async def _validate():
        async with async_session() as db:
            result = await db.execute(
                select(ResearchCall).where(ResearchCall.validated == False)
            )
            research_list = result.scalars().all()
            
            validator = ResearchValidator(db)
            for research in research_list:
                await validator.validate_research(research.id)
    
    asyncio.run(_validate())
