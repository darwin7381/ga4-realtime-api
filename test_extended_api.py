#!/usr/bin/env python3
"""
擴展API測試腳本
測試所有GA4數據查詢端點
"""

import sys
import requests
import json
from typing import Optional

def test_endpoint(base_url: str, endpoint: str, api_key: str, params: dict = None) -> bool:
    """測試API端點"""
    try:
        headers = {"X-API-Key": api_key}
        url = f"{base_url}{endpoint}"
        
        if params:
            response = requests.get(url, headers=headers, params=params, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        
        print(f"📊 {endpoint}")
        print(f"   狀態: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   用戶: {data.get('user', 'N/A')}")
            
            # 根據不同端點顯示關鍵數據
            if 'activeUsers' in str(data):
                print(f"   在線用戶: {data.get('activeUsers', 'N/A')}")
            elif 'data' in data and isinstance(data['data'], dict):
                overview = data['data']
                print(f"   在線用戶: {overview.get('activeUsers', 'N/A')}")
                print(f"   頁面瀏覽: {overview.get('pageViews', 'N/A')}")
            elif 'pages' in data:
                print(f"   頁面數量: {len(data.get('pages', []))}")
            elif 'sources' in data:
                print(f"   流量來源: {len(data.get('sources', []))}")
            elif 'analytics' in data:
                analytics = data['analytics']
                if 'summary' in analytics:
                    print(f"   總瀏覽量: {analytics['summary'].get('totalPageViews', 'N/A')}")
            elif 'devices' in data:
                print(f"   設備類型: {len(data.get('devices', []))}")
            elif 'locations' in data:
                print(f"   地理位置: {len(data.get('locations', []))}")
            
            print(f"   ✅ 成功")
            return True
        else:
            print(f"   ❌ 失敗: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ 錯誤: {str(e)}")
        return False

def main():
    if len(sys.argv) < 3:
        print("用法: python test_extended_api.py <API_URL> <API_KEY>")
        print("範例: python test_extended_api.py http://localhost:8001 abc123")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    api_key = sys.argv[2]
    
    print(f"🧪 測試擴展GA4 API服務: {base_url}")
    print("=" * 60)
    
    # 測試項目
    test_cases = [
        {
            "name": "基本功能測試",
            "tests": [
                ("/health", None),
                ("/active-users", None),
            ]
        },
        {
            "name": "實時數據測試",
            "tests": [
                ("/realtime/overview", None),
                ("/realtime/top-pages", {"limit": 5}),
            ]
        },
        {
            "name": "分析數據測試",
            "tests": [
                ("/analytics/traffic-sources", {"start_date": "7daysAgo", "end_date": "today"}),
                ("/analytics/pageviews", {"start_date": "7daysAgo", "end_date": "today"}),
                ("/analytics/devices", {"start_date": "7daysAgo", "end_date": "today"}),
                ("/analytics/geographic", {"start_date": "7daysAgo", "end_date": "today"}),
            ]
        }
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for category in test_cases:
        print(f"\n📋 {category['name']}")
        print("-" * 40)
        
        for endpoint, params in category['tests']:
            total_tests += 1
            if test_endpoint(base_url, endpoint, api_key, params):
                passed_tests += 1
            print()
    
    # 總結
    print("=" * 60)
    print("📊 測試結果總結:")
    print(f"總測試數: {total_tests}")
    print(f"通過測試: {passed_tests}")
    print(f"失敗測試: {total_tests - passed_tests}")
    print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("\n🎉 所有測試通過！")
        print("📡 可用的API端點:")
        print("   GET /active-users                    # 即時在線人數")
        print("   GET /realtime/overview               # 實時總覽")
        print("   GET /realtime/top-pages              # 實時熱門頁面")
        print("   GET /analytics/traffic-sources       # 流量來源分析")
        print("   GET /analytics/pageviews             # 頁面瀏覽分析")
        print("   GET /analytics/devices               # 設備分析")
        print("   GET /analytics/geographic            # 地理位置數據")
        sys.exit(0)
    else:
        print("\n⚠️  部分測試失敗，請檢查服務狀態")
        sys.exit(1)

if __name__ == "__main__":
    main() 