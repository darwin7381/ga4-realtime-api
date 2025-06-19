#!/usr/bin/env python3
"""
資料庫初始化和管理腳本
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

from database import init_database, test_database_connection, engine
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_tables():
    """創建所有資料庫表格"""
    try:
        success = await init_database()
        if success:
            logger.info("✅ 資料庫表格創建成功")
            return True
        else:
            logger.error("❌ 資料庫表格創建失敗")
            return False
    except Exception as e:
        logger.error(f"❌ 資料庫表格創建異常: {e}")
        return False

async def test_connection():
    """測試資料庫連接"""
    try:
        connected = await test_database_connection()
        if connected:
            logger.info("✅ 資料庫連接測試成功")
            return True
        else:
            logger.error("❌ 資料庫連接測試失敗")
            return False
    except Exception as e:
        logger.error(f"❌ 資料庫連接測試異常: {e}")
        return False

async def drop_tables():
    """刪除所有資料庫表格（危險操作）"""
    if not engine:
        logger.error("❌ 資料庫引擎未初始化")
        return False
    
    confirm = input("⚠️  這將刪除所有資料庫表格，確定要繼續嗎？ (yes/no): ")
    if confirm.lower() != 'yes':
        logger.info("❌ 操作已取消")
        return False
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("✅ 資料庫表格刪除成功")
        return True
    except Exception as e:
        logger.error(f"❌ 資料庫表格刪除失敗: {e}")
        return False

async def reset_database():
    """重置資料庫（刪除並重新創建表格）"""
    logger.info("🔄 開始重置資料庫...")
    
    # 刪除表格
    if await drop_tables():
        # 重新創建表格
        if await create_tables():
            logger.info("✅ 資料庫重置完成")
            return True
    
    logger.error("❌ 資料庫重置失敗")
    return False

async def show_database_info():
    """顯示資料庫資訊"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # 隱藏密碼
        safe_url = database_url.split("://")[0] + "://***:***@" + database_url.split("@")[-1]
        logger.info(f"📊 資料庫 URL: {safe_url}")
    else:
        logger.warning("⚠️  DATABASE_URL 未設定")
    
    # 測試連接
    await test_connection()
    
    # 顯示表格資訊
    if engine:
        try:
            async with engine.begin() as conn:
                result = await conn.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = result.fetchall()
                
                if tables:
                    logger.info(f"📋 現有表格: {', '.join([table[0] for table in tables])}")
                else:
                    logger.info("📋 目前沒有表格")
        except Exception as e:
            logger.error(f"❌ 無法獲取表格資訊: {e}")

def print_usage():
    """顯示使用說明"""
    print("""
資料庫管理工具

使用方式:
    python init_db.py [command]

命令:
    init        - 初始化資料庫表格
    test        - 測試資料庫連接
    info        - 顯示資料庫資訊
    drop        - 刪除所有表格 (危險)
    reset       - 重置資料庫 (刪除並重新創建)
    
範例:
    python init_db.py init
    python init_db.py test
    python init_db.py info
    """)

async def main():
    """主函數"""
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1].lower()
    
    if command == "init":
        await create_tables()
    elif command == "test":
        await test_connection()
    elif command == "info":
        await show_database_info()
    elif command == "drop":
        await drop_tables()
    elif command == "reset":
        await reset_database()
    else:
        print(f"❌ 未知命令: {command}")
        print_usage()

if __name__ == "__main__":
    asyncio.run(main()) 