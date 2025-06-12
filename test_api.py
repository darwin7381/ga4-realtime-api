#!/usr/bin/env python3
"""
簡單的API測試腳本
用法: python test_api.py [API_URL] [API_KEY]
"""

import sys
import requests
import json
from typing import Optional

def test_health_check(base_url: str) -> bool:
    """測試健康檢查端點"""
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"健康檢查狀態: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"服務狀態: {data.get('status')}")
            print(f"檢查項目: {json.dumps(data.get('checks', {}), indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"健康檢查失敗: {response.text}")
            return False
            
    except Exception as e:
        print(f"健康檢查錯誤: {str(e)}")
        return False

def test_active_users(base_url: str, api_key: str) -> bool:
    """測試GA4數據查詢端點"""
    try:
        headers = {"X-API-Key": api_key}
        response = requests.get(f"{base_url}/active-users", headers=headers, timeout=30)
        
        print(f"GA4查詢狀態: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"用戶: {data.get('user')}")
            print(f"在線人數: {data.get('activeUsers')}")
            print(f"查詢時間: {data.get('timestamp')}")
            return True
        else:
            print(f"GA4查詢失敗: {response.text}")
            return False
            
    except Exception as e:
        print(f"GA4查詢錯誤: {str(e)}")
        return False

def test_invalid_api_key(base_url: str) -> bool:
    """測試無效API Key的處理"""
    try:
        headers = {"X-API-Key": "invalid_key_12345"}
        response = requests.get(f"{base_url}/active-users", headers=headers, timeout=10)
        
        print(f"無效API Key測試狀態: {response.status_code}")
        
        if response.status_code == 401:
            print("✅ 無效API Key正確被拒絕")
            return True
        else:
            print(f"❌ 無效API Key處理異常: {response.text}")
            return False
            
    except Exception as e:
        print(f"無效API Key測試錯誤: {str(e)}")
        return False

def main():
    if len(sys.argv) < 2:
        print("用法: python test_api.py <API_URL> [API_KEY]")
        print("範例: python test_api.py https://your-api.railway.app abc123")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"🧪 測試API服務: {base_url}")
    print("=" * 50)
    
    # 測試健康檢查
    print("\n1. 健康檢查測試")
    health_ok = test_health_check(base_url)
    
    # 測試無效API Key
    print("\n2. 無效API Key測試")
    invalid_key_ok = test_invalid_api_key(base_url)
    
    # 測試GA4數據查詢
    if api_key:
        print("\n3. GA4數據查詢測試")
        active_users_ok = test_active_users(base_url, api_key)
    else:
        print("\n3. GA4數據查詢測試 - 跳過 (未提供API Key)")
        active_users_ok = True
    
    # 總結
    print("\n" + "=" * 50)
    print("📊 測試結果總結:")
    print(f"健康檢查: {'✅ 通過' if health_ok else '❌ 失敗'}")
    print(f"安全驗證: {'✅ 通過' if invalid_key_ok else '❌ 失敗'}")
    if api_key:
        print(f"GA4查詢: {'✅ 通過' if active_users_ok else '❌ 失敗'}")
    
    if health_ok and invalid_key_ok and active_users_ok:
        print("\n🎉 所有測試通過！")
        sys.exit(0)
    else:
        print("\n⚠️  部分測試失敗，請檢查配置")
        sys.exit(1)

if __name__ == "__main__":
    main() 