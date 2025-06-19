#!/usr/bin/env python3
"""
GA4 API Service V2 測試腳本
測試雙模式認證 (OAuth + API Key) 功能
"""

import asyncio
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

# 測試配置
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_KEY_JOEY", "abc123def456")  # 使用範例 API Key

class V2APITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def test_health_check(self):
        """測試健康檢查端點"""
        print("🔍 測試健康檢查...")
        try:
            response = await self.client.get(f"{self.base_url}/health")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 健康檢查成功")
                print(f"   狀態: {data.get('status')}")
                print(f"   啟用模式: {data.get('enabled_modes')}")
                print(f"   檢查項目: {data.get('checks')}")
                return True
            else:
                print(f"❌ 健康檢查失敗: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 健康檢查異常: {e}")
            return False
    
    async def test_root_endpoint(self):
        """測試根端點"""
        print("\n🔍 測試根端點...")
        try:
            response = await self.client.get(f"{self.base_url}/")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 根端點成功")
                print(f"   服務: {data.get('service')}")
                print(f"   版本: {data.get('version')}")
                print(f"   功能: {data.get('features')}")
                return True
            else:
                print(f"❌ 根端點失敗: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 根端點異常: {e}")
            return False
    
    async def test_api_key_auth(self):
        """測試 API Key 認證"""
        print("\n🔐 測試 API Key 認證...")
        try:
            headers = {"X-API-Key": API_KEY}
            response = await self.client.get(
                f"{self.base_url}/active-users",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ API Key 認證成功")
                print(f"   用戶: {data.get('user')}")
                print(f"   在線人數: {data.get('activeUsers')}")
                print(f"   時間戳: {data.get('timestamp')}")
                return True
            else:
                print(f"❌ API Key 認證失敗: {response.status_code}")
                if response.status_code == 401:
                    print("   可能原因：API Key 無效或未配置")
                elif response.status_code == 500:
                    print("   可能原因：GA4 配置問題")
                print(f"   響應: {response.text}")
                return False
        
        except Exception as e:
            print(f"❌ API Key 認證異常: {e}")
            return False
    
    async def test_oauth_init(self):
        """測試 OAuth 初始化"""
        print("\n🔐 測試 OAuth 初始化...")
        try:
            response = await self.client.get(f"{self.base_url}/auth/google")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ OAuth 初始化成功")
                print(f"   授權 URL: {data.get('auth_url')[:100]}...")
                print(f"   State: {data.get('state')}")
                print(f"   訊息: {data.get('message')}")
                return True
            elif response.status_code == 501:
                print(f"⚠️  OAuth 模式未啟用")
                return True  # 這是預期的，如果 OAuth 模式未配置
            else:
                print(f"❌ OAuth 初始化失敗: {response.status_code}")
                print(f"   響應: {response.text}")
                return False
        
        except Exception as e:
            print(f"❌ OAuth 初始化異常: {e}")
            return False
    
    async def test_invalid_auth(self):
        """測試無效認證"""
        print("\n🚫 測試無效認證...")
        try:
            # 測試無 API Key
            response = await self.client.get(f"{self.base_url}/active-users")
            
            if response.status_code == 401:
                print(f"✅ 無認證正確被拒絕")
                return True
            else:
                print(f"❌ 無認證應該被拒絕，但返回: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 無效認證測試異常: {e}")
            return False
    
    async def test_invalid_api_key(self):
        """測試無效 API Key"""
        print("\n🚫 測試無效 API Key...")
        try:
            headers = {"X-API-Key": "invalid_key_12345"}
            response = await self.client.get(
                f"{self.base_url}/active-users",
                headers=headers
            )
            
            if response.status_code == 401:
                print(f"✅ 無效 API Key 正確被拒絕")
                return True
            else:
                print(f"❌ 無效 API Key 應該被拒絕，但返回: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 無效 API Key 測試異常: {e}")
            return False
    
    async def test_user_info_without_oauth(self):
        """測試非 OAuth 用戶訪問用戶資訊端點"""
        print("\n🚫 測試 API Key 用戶訪問用戶資訊...")
        try:
            headers = {"X-API-Key": API_KEY}
            response = await self.client.get(
                f"{self.base_url}/user/info",
                headers=headers
            )
            
            if response.status_code == 403:
                print(f"✅ API Key 用戶正確被拒絕訪問用戶資訊端點")
                return True
            else:
                print(f"❌ API Key 用戶應該被拒絕訪問，但返回: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 用戶資訊測試異常: {e}")
            return False
    
    async def run_all_tests(self):
        """執行所有測試"""
        print("🚀 開始 GA4 API Service V2 測試\n")
        
        tests = [
            ("健康檢查", self.test_health_check),
            ("根端點", self.test_root_endpoint),
            ("API Key 認證", self.test_api_key_auth),
            ("OAuth 初始化", self.test_oauth_init),
            ("無效認證", self.test_invalid_auth),
            ("無效 API Key", self.test_invalid_api_key),
            ("API Key 用戶訪問限制", self.test_user_info_without_oauth),
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"❌ {test_name} 測試執行失敗: {e}")
                results.append((test_name, False))
        
        # 測試摘要
        print("\n" + "="*50)
        print("📊 測試結果摘要")
        print("="*50)
        
        passed = 0
        total = len(results)
        
        for test_name, result in results:
            status = "✅ 通過" if result else "❌ 失敗"
            print(f"{status:<8} {test_name}")
            if result:
                passed += 1
        
        print("-"*50)
        print(f"總計: {passed}/{total} 測試通過")
        
        if passed == total:
            print("🎉 所有測試都通過了！")
        else:
            print("⚠️  部分測試失敗，請檢查配置和服務狀態")
        
        await self.client.aclose()
        return passed == total

async def main():
    """主函數"""
    print("GA4 API Service V2 測試工具")
    print("="*50)
    
    # 檢查環境
    print(f"測試目標: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...")
    
    # 執行測試
    tester = V2APITester()
    success = await tester.run_all_tests()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main()) 