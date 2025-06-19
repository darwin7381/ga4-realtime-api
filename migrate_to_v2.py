#!/usr/bin/env python3
"""
GA4 API Service V1 到 V2 遷移助手
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

def check_v1_config():
    """檢查 V1 配置完整性"""
    print("🔍 檢查 V1 配置...")
    
    required_v1_vars = [
        "GA4_PROPERTY_ID",
        "SERVICE_ACCOUNT_JSON"
    ]
    
    missing_vars = []
    for var in required_v1_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    # 檢查 API Keys
    api_keys = []
    for key, value in os.environ.items():
        if key.startswith("API_KEY_"):
            api_keys.append(key)
    
    print(f"✅ GA4 Property ID: {'✓' if os.getenv('GA4_PROPERTY_ID') else '✗'}")
    print(f"✅ Service Account: {'✓' if os.getenv('SERVICE_ACCOUNT_JSON') else '✗'}")
    print(f"✅ API Keys: {len(api_keys)} 個配置")
    
    if missing_vars:
        print(f"❌ 缺少必要的 V1 環境變數: {', '.join(missing_vars)}")
        return False
    
    if not api_keys:
        print("⚠️  沒有配置 API Keys")
        return False
    
    print("✅ V1 配置檢查通過")
    return True

def check_v2_requirements():
    """檢查 V2 新增需求"""
    print("\n🔍 檢查 V2 新增需求...")
    
    oauth_vars = [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET", 
        "OAUTH_REDIRECT_URI"
    ]
    
    oauth_configured = all(os.getenv(var) for var in oauth_vars)
    database_configured = bool(os.getenv("DATABASE_URL"))
    
    print(f"🔐 OAuth 配置: {'✓' if oauth_configured else '✗ (可選)'}")
    print(f"🗄️  資料庫配置: {'✓' if database_configured else '✗ (OAuth 模式需要)'}")
    
    # 功能開關
    oauth_enabled = os.getenv("ENABLE_OAUTH_MODE", "true").lower() == "true"
    api_key_enabled = os.getenv("ENABLE_API_KEY_MODE", "true").lower() == "true"
    
    print(f"🔐 OAuth 模式: {'啟用' if oauth_enabled else '禁用'}")
    print(f"🔑 API Key 模式: {'啟用' if api_key_enabled else '禁用'}")
    
    if oauth_enabled and not oauth_configured:
        print("⚠️  OAuth 模式啟用但未完整配置")
        return False
    
    if oauth_enabled and not database_configured:
        print("⚠️  OAuth 模式需要資料庫但未配置")
        return False
    
    print("✅ V2 需求檢查完成")
    return True

def generate_railway_config():
    """生成 Railway 配置建議"""
    print("\n📋 Railway 配置建議...")
    
    config = {
        "$schema": "https://railway.app/railway.schema.json",
        "build": {
            "builder": "NIXPACKS"
        },
        "deploy": {
            "startCommand": "uvicorn main_v2:app --host 0.0.0.0 --port $PORT",
            "healthcheckPath": "/health",
            "healthcheckTimeout": 100,
            "restartPolicyType": "ON_FAILURE",
            "restartPolicyMaxRetries": 10
        }
    }
    
    import json
    print("建議的 railway.json 配置：")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    return config

def print_migration_checklist():
    """顯示遷移檢查清單"""
    print("\n" + "="*60)
    print("📋 V2 遷移檢查清單")
    print("="*60)
    
    checklist = [
        "[ ] 在 Railway 添加 PostgreSQL 服務",
        "[ ] 在 Google Cloud Console 設定 OAuth 2.0",
        "[ ] 配置 OAUTH_REDIRECT_URI",
        "[ ] 設定所有 V2 環境變數",
        "[ ] 更新 railway.json 啟動命令",
        "[ ] 部署 V2 版本",
        "[ ] 執行 'python init_db.py init'",
        "[ ] 執行 'python test_v2_api.py' 測試",
        "[ ] 驗證 V1 API Key 功能正常",
        "[ ] 測試 OAuth 授權流程",
        "[ ] 監控應用健康狀態"
    ]
    
    for item in checklist:
        print(item)
    
    print("\n" + "="*60)

def print_environment_template():
    """顯示完整的環境變數範本"""
    print("\n📝 完整環境變數範本...")
    print("="*60)
    
    template = """
# V1 兼容配置（必需）
GA4_PROPERTY_ID=319075120
SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# API Keys（V1 兼容）
API_KEY_JOEY=abc123def456
API_KEY_TINA=xyz789uvw012
API_KEY_ADMIN=admin_secret_key_2023

# V2 OAuth 配置（OAuth 模式需要）
GOOGLE_CLIENT_ID=your_client_id.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=https://your-app.railway.app/auth/callback
BASE_URL=https://your-app.railway.app

# 資料庫配置（Railway 自動設定）
DATABASE_URL=postgresql://user:password@host:port/database

# 功能開關
ENABLE_OAUTH_MODE=true
ENABLE_API_KEY_MODE=true
    """
    
    print(template.strip())
    print("="*60)

async def test_database_migration():
    """測試資料庫遷移"""
    print("\n🗄️  測試資料庫功能...")
    
    try:
        from database import test_database_connection, init_database
        
        # 測試連接
        connected = await test_database_connection()
        if connected:
            print("✅ 資料庫連接成功")
            
            # 嘗試初始化
            success = await init_database()
            if success:
                print("✅ 資料庫表格初始化成功")
                return True
            else:
                print("❌ 資料庫表格初始化失敗")
                return False
        else:
            print("❌ 資料庫連接失敗")
            return False
    
    except ImportError:
        print("⚠️  無法導入資料庫模組，請確保依賴項已安裝")
        return False
    except Exception as e:
        print(f"❌ 資料庫測試異常: {e}")
        return False

def main():
    """主函數"""
    print("🚀 GA4 API Service V1 → V2 遷移助手")
    print("="*60)
    
    # 檢查當前配置
    v1_ok = check_v1_config()
    v2_ok = check_v2_requirements()
    
    if not v1_ok:
        print("\n❌ V1 配置不完整，請先確保 V1 功能正常運行")
        sys.exit(1)
    
    # 生成配置
    generate_railway_config()
    
    # 顯示遷移指南
    print_migration_checklist()
    print_environment_template()
    
    # 資料庫測試（如果有 DATABASE_URL）
    if os.getenv("DATABASE_URL"):
        try:
            asyncio.run(test_database_migration())
        except Exception as e:
            print(f"⚠️  資料庫測試跳過: {e}")
    
    print("\n🎉 遷移準備完成！")
    print("請按照檢查清單逐項完成 V2 部署")

if __name__ == "__main__":
    main() 