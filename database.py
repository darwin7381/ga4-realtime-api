import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
import logging

logger = logging.getLogger(__name__)

# 資料庫配置
DATABASE_URL = os.getenv("DATABASE_URL")

# 本地開發：如果 DATABASE_URL 無效，使用 SQLite
def get_database_url():
    """獲取有效的資料庫 URL"""
    if not DATABASE_URL:
        # 使用 SQLite 本地測試
        sqlite_path = "sqlite+aiosqlite:///./test_ga4_v2.db"
        logger.info("使用 SQLite 本地測試資料庫")
        return sqlite_path
    
    # 檢查是否包含模板值
    if any(placeholder in DATABASE_URL for placeholder in ['host', 'port', 'user', 'password', 'database']):
        # 使用 SQLite 本地測試
        sqlite_path = "sqlite+aiosqlite:///./test_ga4_v2.db"
        logger.warning("DATABASE_URL 包含模板值，改用 SQLite 本地測試")
        return sqlite_path
    
    # Railway PostgreSQL URL 轉換
    if DATABASE_URL.startswith("postgres://"):
        converted_url = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        logger.info("使用 PostgreSQL 生產資料庫")
        return converted_url
    
    return DATABASE_URL

# 獲取實際使用的 DATABASE_URL
ACTUAL_DATABASE_URL = get_database_url()

# 建立資料庫引擎
engine = None
async_session_factory = None

try:
    engine = create_async_engine(
        ACTUAL_DATABASE_URL,
        echo=False,  # 設為 True 可以看到 SQL 查詢日誌
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    logger.info(f"資料庫引擎初始化成功：{ACTUAL_DATABASE_URL.split('://')[0].upper()}")
except Exception as e:
    logger.error(f"資料庫引擎初始化失敗: {e}")
    raise

# 基礎模型類
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s"
    })

# 資料庫會話依賴
async def get_db() -> AsyncSession:
    """取得資料庫會話"""
    if not async_session_factory:
        raise RuntimeError("資料庫未初始化")
    
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

# 資料庫初始化
async def init_database():
    """初始化資料庫表格"""
    if not engine:
        logger.error("資料庫引擎未初始化")
        return False
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("資料庫表格初始化完成")
        return True
    except Exception as e:
        logger.error(f"資料庫初始化失敗: {e}")
        return False

# 資料庫連接測試
async def test_database_connection():
    """測試資料庫連接"""
    if not engine:
        return False
    
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"資料庫連接測試失敗: {e}")
        return False 