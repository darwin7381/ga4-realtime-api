#!/usr/bin/env python3
"""
環境變數檢查工具
用於診斷 .env 配置問題
"""

import os
import json
from dotenv import load_dotenv

def check_env_variables():
    """檢查所有必要的環境變數"""
    print("🔍 環境變數檢查工具")
    print("=" * 50)
    
    # 載入 .env 文件
    print("📁 載入 .env 文件...")
    load_dotenv()
    
    # 檢查GA4配置
    print("\n1. GA4 配置檢查:")
    ga4_property_id = os.getenv("GA4_PROPERTY_ID")
    if ga4_property_id:
        print(f"   ✅ GA4_PROPERTY_ID: {ga4_property_id}")
    else:
        print("   ❌ GA4_PROPERTY_ID: 未設定")
    
    # 檢查Service Account JSON
    print("\n2. Service Account JSON 檢查:")
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            # 嘗試解析JSON
            parsed_json = json.loads(service_account_json)
            print("   ✅ SERVICE_ACCOUNT_JSON: 格式正確")
            print(f"   📧 Client Email: {parsed_json.get('client_email', 'N/A')}")
            print(f"   🏗️  Project ID: {parsed_json.get('project_id', 'N/A')}")
            
            # 檢查必要欄位
            required_fields = ['type', 'project_id', 'private_key', 'client_email']
            missing_fields = [field for field in required_fields if field not in parsed_json]
            
            if missing_fields:
                print(f"   ⚠️  缺少必要欄位: {', '.join(missing_fields)}")
            else:
                print("   ✅ 包含所有必要欄位")
                
        except json.JSONDecodeError as e:
            print(f"   ❌ SERVICE_ACCOUNT_JSON: JSON格式錯誤 - {str(e)}")
            print("   💡 提示: 確保JSON在同一行，且使用 \\\\n 表示換行")
    else:
        print("   ❌ SERVICE_ACCOUNT_JSON: 未設定")
    
    # 檢查API Keys
    print("\n3. API Keys 檢查:")
    api_keys = {}
    api_key_count = 0
    
    for key, value in os.environ.items():
        if key.startswith("API_KEY_"):
            user_name = key.replace("API_KEY_", "").lower()
            api_keys[value] = user_name
            api_key_count += 1
            print(f"   ✅ {key}: {value[:8]}...{value[-4:]} (用戶: {user_name})")
    
    if api_key_count == 0:
        print("   ❌ 未找到任何API Key")
        print("   💡 提示: API Key格式應為 API_KEY_USERNAME=your_key")
    else:
        print(f"   📊 總計: {api_key_count} 個API Key")
    
    # 總結
    print("\n" + "=" * 50)
    print("📊 檢查結果總結:")
    
    issues = []
    if not ga4_property_id:
        issues.append("GA4_PROPERTY_ID 未設定")
    if not service_account_json:
        issues.append("SERVICE_ACCOUNT_JSON 未設定")
    elif service_account_json:
        try:
            json.loads(service_account_json)
        except:
            issues.append("SERVICE_ACCOUNT_JSON 格式錯誤")
    if api_key_count == 0:
        issues.append("未設定任何API Key")
    
    if issues:
        print("❌ 發現問題:")
        for issue in issues:
            print(f"   • {issue}")
        print("\n💡 請參考 '本地開發說明.md' 修正這些問題")
        return False
    else:
        print("✅ 所有配置正確！")
        print("🚀 您現在可以啟動服務: python main.py")
        return True

def show_sample_env():
    """顯示 .env 文件範例"""
    print("\n📝 正確的 .env 文件範例:")
    print("-" * 40)
    print("GA4_PROPERTY_ID=319075120")
    print("SERVICE_ACCOUNT_JSON={\"type\":\"service_account\",\"project_id\":\"your-project\",...}")
    print("API_KEY_JOEY=abc123def456")
    print("API_KEY_TINA=xyz789uvw012")
    print("-" * 40)

if __name__ == "__main__":
    success = check_env_variables()
    
    if not success:
        show_sample_env()
    
    print(f"\n🏃‍♂️ 如需測試API，請執行:")
    print("python test_api.py http://localhost:8000 your_api_key") 