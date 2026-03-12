import os
from functools import lru_cache
from typing import Optional


class Settings:
    def __init__(self):
        self.kite_api_key = os.getenv("KITE_API_KEY", "")
        self.kite_api_secret = os.getenv("KITE_API_SECRET", "")
        self.kite_request_token = os.getenv("KITE_REQUEST_TOKEN", "")
        self.kite_access_token = os.getenv("KITE_ACCESS_TOKEN", "")
        
        self.telegram_api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        self.telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.telegram_session_string = os.getenv("TELEGRAM_SESSION_STRING", "")
        self.telegram_channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        
        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.postgres_user = os.getenv("POSTGRES_USER", "tradingbot")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", "")
        self.postgres_db = os.getenv("POSTGRES_DB", "tradingbot")
        
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", "")
        
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        self.default_quantity = int(os.getenv("DEFAULT_QUANTITY", "1"))
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE", "1.0"))
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", "10000"))
        self.max_positions = int(os.getenv("MAX_POSITIONS", "5"))
        
        self.paper_trading = os.getenv("PAPER_TRADING", "true").lower() == "true"
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def sync_database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
