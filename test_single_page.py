#!/usr/bin/env python3
"""
單篇頁面分析功能測試腳本
測試新的 /analytics/single-page 端點
"""

import requests
import json
import sys

def test_single_page_analytics(base_url: str, api_key: str, page_path: str):
    """測試單篇頁面分析功能"""
    
    print(f"🧪 測試單篇頁面分析功能")
    print(f"目標API: {base_url}")
    print(f"頁面路徑: {page_path}")
    print("=" * 60)
    
    # 測試參數
    params = {
        "page_path": page_path,
        "start_date": "7daysAgo",
        "end_date": "today"
    }
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        # 發送請求
        print("📡 發送請求...")
        response = requests.get(
            f"{base_url}/analytics/single-page",
            params=params,
            headers=headers,
            timeout=30
        )
        
        print(f"📊 響應狀態: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 檢查響應狀態
            if data.get("status") == "not_found":
                print("⚠️  未找到該頁面的數據")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                return False
            
            print("✅ 請求成功！")
            print()
            
            # 基本信息
            page_data = data.get("pageData", {})
            print(f"👤 用戶: {data.get('user')}")
            print(f"📄 頁面路徑: {page_data.get('pagePath')}")
            print(f"📝 頁面標題: {page_data.get('pageTitle', '未知')}")
            print(f"📅 查詢期間: {data.get('dateRange')}")
            print()
            
            # 摘要數據
            summary = page_data.get("summary", {})
            print("📊 摘要數據:")
            print(f"  總頁面瀏覽: {summary.get('totalPageViews', 0):,}")
            print(f"  總用戶數: {summary.get('totalUsers', 0):,}")
            print(f"  總會話數: {summary.get('totalSessions', 0):,}")
            print(f"  新用戶: {summary.get('newUsers', 0):,}")
            print(f"  平均跳出率: {summary.get('avgBounceRate', 0):.2f}%")
            print(f"  平均參與率: {summary.get('avgEngagementRate', 0):.2f}%")
            print(f"  平均會話時長: {summary.get('avgSessionDuration', 0):.2f} 秒")
            print(f"  性能等級: {summary.get('performanceGrade', '未知')}")
            print()
            
            # 每日數據 (顯示前3天)
            daily_data = page_data.get("dailyBreakdown", [])
            if daily_data:
                print("📈 每日數據 (最近3天):")
                for i, day in enumerate(daily_data[-3:]):
                    print(f"  {day.get('date')}: {day.get('pageViews')} 瀏覽, {day.get('users')} 用戶")
                print()
            
            # 流量來源 (顯示前3個)
            traffic_sources = page_data.get("trafficSources", [])
            if traffic_sources:
                print("🌐 主要流量來源:")
                for i, source in enumerate(traffic_sources[:3]):
                    print(f"  {i+1}. {source.get('channelGroup')} - {source.get('source')}: {source.get('sessions')} 會話")
                print()
            
            # 設備分布 (顯示前3個)
            device_breakdown = page_data.get("deviceBreakdown", [])
            if device_breakdown:
                print("📱 設備分布:")
                for i, device in enumerate(device_breakdown[:3]):
                    print(f"  {i+1}. {device.get('deviceCategory')} ({device.get('operatingSystem')}): {device.get('users')} 用戶")
                print()
            
            return True
            
        else:
            print(f"❌ 請求失敗: {response.status_code}")
            try:
                error_data = response.json()
                print(f"錯誤信息: {error_data.get('error', '未知錯誤')}")
            except:
                print(f"錯誤內容: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ 請求異常: {str(e)}")
        return False

def main():
    if len(sys.argv) < 4:
        print("用法: python test_single_page.py <API_URL> <API_KEY> <PAGE_PATH>")
        print()
        print("範例:")
        print("  # 使用頁面路徑")
        print("  python test_single_page.py https://ga4.blocktempo.ai your_api_key /iran-bans-crypto-night/")
        print()
        print("  # 使用完整URL")
        print("  python test_single_page.py https://ga4.blocktempo.ai your_api_key https://www.blocktempo.com/some-article/")
        print()
        print("  # 測試本地開發")
        print("  python test_single_page.py http://localhost:8000 your_api_key /article-path/")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    api_key = sys.argv[2]
    page_path = sys.argv[3]
    
    # 執行測試
    success = test_single_page_analytics(base_url, api_key, page_path)
    
    print("=" * 60)
    if success:
        print("🎉 測試完成！新功能運作正常")
        sys.exit(0)
    else:
        print("⚠️  測試失敗，請檢查配置和網路連接")
        sys.exit(1)

if __name__ == "__main__":
    main() 