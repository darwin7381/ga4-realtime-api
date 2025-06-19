"""
GA4 API 擴展模組
提供更多常用的GA4數據查詢功能
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunRealtimeReportRequest,
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
    OrderBy
)
from google.oauth2 import service_account
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class GA4DataService:
    """GA4數據服務類"""
    
    def __init__(self):
        self.property_id = os.getenv("GA4_PROPERTY_ID")
        self.client = self._get_client()
    
    def _get_client(self):
        """初始化GA4客戶端"""
        service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
        if not service_account_json:
            raise ValueError("SERVICE_ACCOUNT_JSON 環境變數未設定")
        
        credentials_info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
        
        return BetaAnalyticsDataClient(credentials=credentials)
    
    def get_realtime_overview(self) -> Dict:
        """獲取實時總覽數據"""
        request = RunRealtimeReportRequest(
            property=f"properties/{self.property_id}",
            metrics=[
                {"name": "activeUsers"},
                {"name": "screenPageViews"},
                {"name": "eventCount"}
            ],
            dimensions=[
                {"name": "country"},
                {"name": "deviceCategory"}
            ],
            limit=10
        )
        
        response = self.client.run_realtime_report(request=request)
        
        # 解析數據
        active_users = 0
        page_views = 0
        events = 0
        countries = []
        devices = []
        
        if response.rows:
            for row in response.rows:
                active_users += int(row.metric_values[0].value)
                page_views += int(row.metric_values[1].value)
                events += int(row.metric_values[2].value)
                
                country = row.dimension_values[0].value
                device = row.dimension_values[1].value
                
                if country not in [c["name"] for c in countries]:
                    countries.append({
                        "name": country,
                        "users": int(row.metric_values[0].value)
                    })
                
                if device not in [d["name"] for d in devices]:
                    devices.append({
                        "name": device,
                        "users": int(row.metric_values[0].value)
                    })
        
        return {
            "activeUsers": active_users,
            "pageViews": page_views,
            "events": events,
            "topCountries": sorted(countries, key=lambda x: x["users"], reverse=True)[:5],
            "deviceBreakdown": devices
        }
    
    def get_realtime_top_pages(self, limit: int = 10) -> List[Dict]:
        """獲取實時熱門頁面 (注意：GA4實時API對URL路徑支援有限)"""
        # 嘗試獲取帶有路徑的實時數據
        try:
            request = RunRealtimeReportRequest(
                property=f"properties/{self.property_id}",
                metrics=[
                    {"name": "activeUsers"},
                    {"name": "screenPageViews"}
                ],
                dimensions=[
                    {"name": "pagePath"},
                    {"name": "pageTitle"}
                ],
                order_bys=[OrderBy(metric={"metric_name": "activeUsers"}, desc=True)],
                limit=limit
            )
            
            response = self.client.run_realtime_report(request=request)
            
            pages = []
            if response.rows:
                for row in response.rows:
                    pages.append({
                        "pagePath": row.dimension_values[0].value,
                        "pageTitle": row.dimension_values[1].value if len(row.dimension_values) > 1 else "未知標題",
                        "activeUsers": int(row.metric_values[0].value),
                        "pageViews": int(row.metric_values[1].value)
                    })
                return pages
        except Exception as e:
            logger.warning(f"無法取得實時頁面路徑數據，回退至螢幕名稱: {e}")
        
        # 回退方案：使用screenName
        request = RunRealtimeReportRequest(
            property=f"properties/{self.property_id}",
            metrics=[
                {"name": "activeUsers"},
                {"name": "screenPageViews"}
            ],
            dimensions=[
                {"name": "unifiedScreenName"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "activeUsers"}, desc=True)],
            limit=limit
        )
        
        response = self.client.run_realtime_report(request=request)
        
        pages = []
        if response.rows:
            for row in response.rows:
                pages.append({
                    "screenName": row.dimension_values[0].value,
                    "note": "實時API限制：無法提供完整URL路徑",
                    "activeUsers": int(row.metric_values[0].value),
                    "pageViews": int(row.metric_values[1].value)
                })
        
        return pages
    
    def get_top_pages_analytics(self, start_date: str = "1daysAgo", end_date: str = "today", limit: int = 20) -> List[Dict]:
        """獲取熱門頁面分析數據 (包含完整URL路徑)"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "screenPageViews"},
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"}
            ],
            dimensions=[
                {"name": "pagePath"},
                {"name": "pageTitle"},
                {"name": "fullPageUrl"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "screenPageViews"}, desc=True)],
            limit=limit
        )
        
        response = self.client.run_report(request=request)
        
        pages = []
        if response.rows:
            for row in response.rows:
                pages.append({
                    "pagePath": row.dimension_values[0].value,
                    "pageTitle": row.dimension_values[1].value if len(row.dimension_values) > 1 else "未知標題",
                    "fullUrl": row.dimension_values[2].value if len(row.dimension_values) > 2 else "",
                    "pageViews": int(row.metric_values[0].value),
                    "totalUsers": int(row.metric_values[1].value),
                    "sessions": int(row.metric_values[2].value),
                    "avgSessionDuration": round(float(row.metric_values[3].value), 2),
                    "bounceRate": round(float(row.metric_values[4].value) * 100, 2)
                })
        
        return pages
    
    def get_traffic_sources(self, start_date: str = "7daysAgo", end_date: str = "today") -> List[Dict]:
        """獲取流量來源數據"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "newUsers"},
                {"name": "bounceRate"}
            ],
            dimensions=[
                {"name": "sessionDefaultChannelGroup"},
                {"name": "sessionSource"},
                {"name": "sessionMedium"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "sessions"}, desc=True)],
            limit=20
        )
        
        response = self.client.run_report(request=request)
        
        sources = []
        if response.rows:
            for row in response.rows:
                sources.append({
                    "channelGroup": row.dimension_values[0].value,
                    "source": row.dimension_values[1].value,
                    "medium": row.dimension_values[2].value,
                    "sessions": int(row.metric_values[0].value),
                    "totalUsers": int(row.metric_values[1].value),
                    "newUsers": int(row.metric_values[2].value),
                    "bounceRate": round(float(row.metric_values[3].value) * 100, 2)
                })
        
        return sources
    
    def get_pageviews_analytics(self, start_date: str = "7daysAgo", end_date: str = "today") -> Dict:
        """獲取頁面瀏覽分析數據"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "screenPageViews"},
                {"name": "sessions"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"}
            ],
            dimensions=[
                {"name": "pagePath"},
                {"name": "pageTitle"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "screenPageViews"}, desc=True)],
            limit=20
        )
        
        response = self.client.run_report(request=request)
        
        total_pageviews = 0
        total_unique_views = 0
        pages = []
        
        if response.rows:
            for row in response.rows:
                pageviews = int(row.metric_values[0].value)
                sessions = int(row.metric_values[1].value)
                avg_duration = float(row.metric_values[2].value)
                bounce_rate = float(row.metric_values[3].value) * 100
                
                total_pageviews += pageviews
                total_unique_views += sessions
                
                pages.append({
                    "path": row.dimension_values[0].value,
                    "title": row.dimension_values[1].value or "未知標題",
                    "pageViews": pageviews,
                    "sessions": sessions,
                    "avgSessionDuration": round(avg_duration, 2),
                    "bounceRate": round(bounce_rate, 2)
                })
        
        return {
            "summary": {
                "totalPageViews": total_pageviews,
                "totalUniqueViews": total_unique_views,
                "totalPages": len(pages)
            },
            "topPages": pages
        }
    
    def get_device_analytics(self, start_date: str = "7daysAgo", end_date: str = "today") -> List[Dict]:
        """獲取設備分析數據"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "bounceRate"},
                {"name": "averageSessionDuration"}
            ],
            dimensions=[
                {"name": "deviceCategory"},
                {"name": "operatingSystem"},
                {"name": "browser"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "totalUsers"}, desc=True)],
            limit=15
        )
        
        response = self.client.run_report(request=request)
        
        devices = []
        if response.rows:
            for row in response.rows:
                devices.append({
                    "deviceCategory": row.dimension_values[0].value,
                    "operatingSystem": row.dimension_values[1].value,
                    "browser": row.dimension_values[2].value,
                    "totalUsers": int(row.metric_values[0].value),
                    "sessions": int(row.metric_values[1].value),
                    "bounceRate": round(float(row.metric_values[2].value) * 100, 2),
                    "avgSessionDuration": round(float(row.metric_values[3].value), 2)
                })
        
        return devices
    
    def get_geographic_data(self, start_date: str = "7daysAgo", end_date: str = "today") -> List[Dict]:
        """獲取地理位置數據"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"}
            ],
            dimensions=[
                {"name": "country"},
                {"name": "city"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "totalUsers"}, desc=True)],
            limit=20
        )
        
        response = self.client.run_report(request=request)
        
        locations = []
        if response.rows:
            for row in response.rows:
                locations.append({
                    "country": row.dimension_values[0].value,
                    "city": row.dimension_values[1].value,
                    "totalUsers": int(row.metric_values[0].value),
                    "sessions": int(row.metric_values[1].value),
                    "pageViews": int(row.metric_values[2].value)
                })
        
        return locations 
    
    def get_search_terms(self, start_date: str = "7daysAgo", end_date: str = "today", limit: int = 20) -> List[Dict]:
        """獲取站內搜索數據"""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"},
                {"name": "averageSessionDuration"}
            ],
            dimensions=[
                {"name": "searchTerm"},
                {"name": "pagePath"}
            ],
            # 注意：站內搜索需要GA4設置才能工作，先嘗試不使用過濾器
            order_bys=[OrderBy(metric={"metric_name": "totalUsers"}, desc=True)],
            limit=limit
        )
        
        response = self.client.run_report(request=request)
        
        searches = []
        if response.rows:
            for row in response.rows:
                searches.append({
                    "searchTerm": row.dimension_values[0].value,
                    "searchPage": row.dimension_values[1].value if len(row.dimension_values) > 1 else "",
                    "totalUsers": int(row.metric_values[0].value),
                    "sessions": int(row.metric_values[1].value),
                    "pageViews": int(row.metric_values[2].value),
                    "avgSessionDuration": round(float(row.metric_values[3].value), 2)
                })
        
        return searches
    
    def get_performance_metrics(self, start_date: str = "7daysAgo", end_date: str = "today", limit: int = 20) -> Dict:
        """獲取頁面效能數據 (Core Web Vitals)"""
        # 頁面載入時間數據
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"},
                {"name": "screenPageViews"},
                {"name": "engagementRate"},
                {"name": "sessionsPerUser"}
            ],
            dimensions=[
                {"name": "pagePath"},
                {"name": "pageTitle"},
                {"name": "deviceCategory"}
            ],
            order_bys=[OrderBy(metric={"metric_name": "screenPageViews"}, desc=True)],
            limit=limit
        )
        
        response = self.client.run_report(request=request)
        
        pages_performance = []
        total_bounce_rate = 0
        total_engagement_rate = 0
        total_pages = 0
        
        if response.rows:
            for row in response.rows:
                bounce_rate = float(row.metric_values[1].value) * 100
                engagement_rate = float(row.metric_values[3].value) * 100
                
                total_bounce_rate += bounce_rate
                total_engagement_rate += engagement_rate
                total_pages += 1
                
                pages_performance.append({
                    "pagePath": row.dimension_values[0].value,
                    "pageTitle": row.dimension_values[1].value if len(row.dimension_values) > 1 else "未知標題",
                    "deviceCategory": row.dimension_values[2].value if len(row.dimension_values) > 2 else "未知設備",
                    "avgSessionDuration": round(float(row.metric_values[0].value), 2),
                    "bounceRate": round(bounce_rate, 2),
                    "pageViews": int(row.metric_values[2].value),
                    "engagementRate": round(engagement_rate, 2),
                    "sessionsPerUser": round(float(row.metric_values[4].value), 2)
                })
        
        # 計算整體效能指標
        avg_bounce_rate = round(total_bounce_rate / total_pages, 2) if total_pages > 0 else 0
        avg_engagement_rate = round(total_engagement_rate / total_pages, 2) if total_pages > 0 else 0
        
        return {
            "summary": {
                "totalPagesAnalyzed": total_pages,
                "avgBounceRate": avg_bounce_rate,
                "avgEngagementRate": avg_engagement_rate,
                "performanceGrade": self._calculate_performance_grade(avg_bounce_rate, avg_engagement_rate)
            },
            "pagePerformance": pages_performance
        }
    
    def get_single_page_analytics(self, page_path: str, start_date: str = "7daysAgo", end_date: str = "today") -> Dict:
        """獲取單篇頁面的詳細分析數據"""
        # 處理URL，提取路徑部分
        if page_path.startswith("http"):
            from urllib.parse import urlparse
            parsed = urlparse(page_path)
            page_path = parsed.path
        
        # 確保路徑以 / 開始
        if not page_path.startswith("/"):
            page_path = "/" + page_path
        
        # 使用篩選器查詢特定頁面
        from google.analytics.data_v1beta.types import FilterExpression, Filter
        
        # 創建頁面路徑篩選器
        path_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=page_path
                )
            )
        )
        
        # 基礎數據查詢
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "screenPageViews"},
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"},
                {"name": "engagementRate"},
                {"name": "newUsers"},
                {"name": "userEngagementDuration"}
            ],
            dimensions=[
                {"name": "pagePath"},
                {"name": "pageTitle"},
                {"name": "date"}
            ],
            dimension_filter=path_filter,
            order_bys=[OrderBy(dimension={"dimension_name": "date"}, desc=False)],
            limit=100
        )
        
        response = self.client.run_report(request=request)
        
        if not response.rows:
            return {
                "error": "未找到該頁面的數據",
                "pagePath": page_path,
                "dateRange": f"{start_date} to {end_date}",
                "suggestions": [
                    "請確認頁面路徑是否正確",
                    "該頁面可能在指定時間範圍內沒有訪問數據",
                    "請檢查URL格式是否正確"
                ]
            }
        
        # 匯總數據
        total_pageviews = 0
        total_users = 0
        total_sessions = 0
        total_engagement_duration = 0
        daily_data = []
        page_title = "未知標題"
        
        for row in response.rows:
            pageviews = int(row.metric_values[0].value)
            users = int(row.metric_values[1].value)
            sessions = int(row.metric_values[2].value)
            avg_duration = float(row.metric_values[3].value)
            bounce_rate = float(row.metric_values[4].value) * 100
            engagement_rate = float(row.metric_values[5].value) * 100
            new_users = int(row.metric_values[6].value)
            engagement_duration = float(row.metric_values[7].value)
            
            total_pageviews += pageviews
            total_users += users
            total_sessions += sessions
            total_engagement_duration += engagement_duration
            
            if not page_title or page_title == "未知標題":
                page_title = row.dimension_values[1].value if len(row.dimension_values) > 1 else "未知標題"
            
            daily_data.append({
                "date": row.dimension_values[2].value,
                "pageViews": pageviews,
                "users": users,
                "sessions": sessions,
                "avgSessionDuration": round(avg_duration, 2),
                "bounceRate": round(bounce_rate, 2),
                "engagementRate": round(engagement_rate, 2),
                "newUsers": new_users
            })
        
        # 計算平均值
        avg_bounce_rate = sum(day["bounceRate"] for day in daily_data) / len(daily_data) if daily_data else 0
        avg_engagement_rate = sum(day["engagementRate"] for day in daily_data) / len(daily_data) if daily_data else 0
        avg_session_duration = total_engagement_duration / total_sessions if total_sessions > 0 else 0
        
        # 獲取流量來源數據（針對此頁面）
        traffic_sources = self._get_page_traffic_sources(page_path, start_date, end_date)
        
        # 獲取設備分布數據（針對此頁面）
        device_breakdown = self._get_page_device_breakdown(page_path, start_date, end_date)
        
        return {
            "pagePath": page_path,
            "pageTitle": page_title,
            "dateRange": f"{start_date} to {end_date}",
            "summary": {
                "totalPageViews": total_pageviews,
                "totalUsers": total_users,
                "totalSessions": total_sessions,
                "newUsers": sum(day["newUsers"] for day in daily_data),
                "avgBounceRate": round(avg_bounce_rate, 2),
                "avgEngagementRate": round(avg_engagement_rate, 2),
                "avgSessionDuration": round(avg_session_duration, 2),
                "performanceGrade": self._calculate_performance_grade(avg_bounce_rate, avg_engagement_rate)
            },
            "dailyBreakdown": daily_data,
            "trafficSources": traffic_sources,
            "deviceBreakdown": device_breakdown
        }
    
    def _get_page_traffic_sources(self, page_path: str, start_date: str, end_date: str) -> List[Dict]:
        """獲取特定頁面的流量來源"""
        from google.analytics.data_v1beta.types import FilterExpression, Filter
        
        path_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=page_path
                )
            )
        )
        
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"}
            ],
            dimensions=[
                {"name": "sessionDefaultChannelGroup"},
                {"name": "sessionSource"},
                {"name": "sessionMedium"}
            ],
            dimension_filter=path_filter,
            order_bys=[OrderBy(metric={"metric_name": "sessions"}, desc=True)],
            limit=10
        )
        
        response = self.client.run_report(request=request)
        
        sources = []
        if response.rows:
            for row in response.rows:
                sources.append({
                    "channelGroup": row.dimension_values[0].value,
                    "source": row.dimension_values[1].value,
                    "medium": row.dimension_values[2].value,
                    "sessions": int(row.metric_values[0].value),
                    "users": int(row.metric_values[1].value),
                    "pageViews": int(row.metric_values[2].value)
                })
        
        return sources
    
    def _get_page_device_breakdown(self, page_path: str, start_date: str, end_date: str) -> List[Dict]:
        """獲取特定頁面的設備分布"""
        from google.analytics.data_v1beta.types import FilterExpression, Filter
        
        path_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=page_path
                )
            )
        )
        
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"}
            ],
            dimensions=[
                {"name": "deviceCategory"},
                {"name": "operatingSystem"}
            ],
            dimension_filter=path_filter,
            order_bys=[OrderBy(metric={"metric_name": "totalUsers"}, desc=True)],
            limit=10
        )
        
        response = self.client.run_report(request=request)
        
        devices = []
        if response.rows:
            for row in response.rows:
                devices.append({
                    "deviceCategory": row.dimension_values[0].value,
                    "operatingSystem": row.dimension_values[1].value,
                    "users": int(row.metric_values[0].value),
                    "sessions": int(row.metric_values[1].value),
                    "pageViews": int(row.metric_values[2].value)
                })
        
        return devices

    def _calculate_performance_grade(self, bounce_rate: float, engagement_rate: float) -> str:
        """計算網站效能等級"""
        if bounce_rate < 25 and engagement_rate > 70:
            return "A+ (優秀)"
        elif bounce_rate < 40 and engagement_rate > 60:
            return "A (良好)"
        elif bounce_rate < 55 and engagement_rate > 45:
            return "B (一般)"
        elif bounce_rate < 70 and engagement_rate > 30:
            return "C (需改善)"
        else:
            return "D (急需優化)"