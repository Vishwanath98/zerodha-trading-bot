from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.models import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database dependency."""
    async with async_session() as session:
        yield session
