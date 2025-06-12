import os
import json
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunRealtimeReportRequest
from google.oauth2 import service_account
from pydantic import BaseModel
import time

# 導入GA4擴展功能
from ga4_extensions import GA4DataService

# 載入環境變數 (本地開發用)
load_dotenv()

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI 應用初始化
app = FastAPI(
    title="GA4 Realtime API Service",
    description="BlockTempo GA4 即時在線人數查詢服務",
    version="1.0.0"
)

# CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 響應模型
class ActiveUsersResponse(BaseModel):
    user: str
    activeUsers: int
    timestamp: str
    status: str = "success"

class ErrorResponse(BaseModel):
    error: str
    message: str
    timestamp: str

class RealtimeOverviewResponse(BaseModel):
    user: str
    data: Dict
    timestamp: str
    status: str = "success"

class TopPagesResponse(BaseModel):
    user: str
    pages: List[Dict]
    timestamp: str
    status: str = "success"

class TrafficSourcesResponse(BaseModel):
    user: str
    sources: List[Dict]
    dateRange: str
    timestamp: str
    status: str = "success"

class PageAnalyticsResponse(BaseModel):
    user: str
    analytics: Dict
    dateRange: str
    timestamp: str
    status: str = "success"

class DeviceAnalyticsResponse(BaseModel):
    user: str
    devices: List[Dict]
    dateRange: str
    timestamp: str
    status: str = "success"

class GeographicDataResponse(BaseModel):
    user: str
    locations: List[Dict]
    dateRange: str
    timestamp: str
    status: str = "success"

# 配置和常量
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")

# API Key 配置 - 從環境變數載入
def load_api_keys() -> Dict[str, str]:
    """載入API Key配置，格式：API_KEY_[USER]=key"""
    api_keys = {}
    for key, value in os.environ.items():
        if key.startswith("API_KEY_"):
            user_name = key.replace("API_KEY_", "").lower()
            api_keys[value] = user_name
    
    if not api_keys:
        logger.warning("未找到任何API Key配置")
    else:
        logger.info(f"已載入 {len(api_keys)} 個API Key")
    
    return api_keys

API_KEYS = load_api_keys()

# 速率限制配置
class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, api_key: str) -> bool:
        now = time.time()
        if api_key not in self.requests:
            self.requests[api_key] = []
        
        # 清理過期記錄
        self.requests[api_key] = [
            req_time for req_time in self.requests[api_key]
            if now - req_time < self.time_window
        ]
        
        # 檢查是否超過限制
        if len(self.requests[api_key]) >= self.max_requests:
            return False
        
        # 記錄此次請求
        self.requests[api_key].append(now)
        return True

rate_limiter = RateLimiter(max_requests=200, time_window=600)

# 初始化GA4數據服務
try:
    ga4_service = GA4DataService()
    logger.info("GA4DataService 初始化成功")
except Exception as e:
    logger.warning(f"GA4DataService 初始化失敗: {str(e)}")
    ga4_service = None

# GA4 客戶端初始化
def get_ga4_client():
    """初始化GA4客戶端"""
    try:
        if not SERVICE_ACCOUNT_JSON:
            raise ValueError("SERVICE_ACCOUNT_JSON 環境變數未設定")
        
        # 解析Service Account JSON
        credentials_info = json.loads(SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
        
        client = BetaAnalyticsDataClient(credentials=credentials)
        logger.info("GA4客戶端初始化成功")
        return client
    
    except Exception as e:
        logger.error(f"GA4客戶端初始化失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4服務初始化失敗"
        )

# API Key 驗證
def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """驗證API Key並返回用戶名"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-API-Key 標頭"
        )
    
    if x_api_key not in API_KEYS:
        logger.warning(f"無效的API Key嘗試: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的API Key"
        )
    
    # 速率限制檢查
    if not rate_limiter.is_allowed(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="請求頻率過高，請稍後再試"
        )
    
    return API_KEYS[x_api_key]

# 路由定義
@app.get("/", response_model=dict)
async def root():
    """健康檢查端點"""
    return {
        "service": "GA4 Realtime API Service",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health", response_model=dict)
async def health_check():
    """詳細健康檢查"""
    checks = {
        "api_service": "ok",
        "ga4_property_configured": bool(GA4_PROPERTY_ID),
        "service_account_configured": bool(SERVICE_ACCOUNT_JSON),
        "api_keys_loaded": len(API_KEYS) > 0
    }
    
    all_ok = all(checks.values())
    
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/active-users", response_model=ActiveUsersResponse)
async def get_active_users(x_api_key: Optional[str] = Header(None)):
    """取得GA4即時在線人數"""
    
    # API Key驗證
    user_name = verify_api_key(x_api_key)
    
    try:
        # 檢查必要配置
        if not GA4_PROPERTY_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GA4_PROPERTY_ID 未配置"
            )
        
        # 初始化GA4客戶端
        client = get_ga4_client()
        
        # 建立請求
        request = RunRealtimeReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            metrics=[{"name": "activeUsers"}]
        )
        
        logger.info(f"用戶 {user_name} 請求GA4數據")
        
        # 執行請求
        response = client.run_realtime_report(request=request)
        
        # 解析響應
        active_users = 0
        if response.rows:
            active_users = int(response.rows[0].metric_values[0].value)
        
        logger.info(f"GA4查詢成功 - 用戶: {user_name}, 在線人數: {active_users}")
        
        return ActiveUsersResponse(
            user=user_name,
            activeUsers=active_users,
            timestamp=datetime.now().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GA4查詢失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GA4查詢失敗: {str(e)}"
        )

@app.get("/realtime/overview", response_model=RealtimeOverviewResponse)
async def get_realtime_overview(x_api_key: Optional[str] = Header(None)):
    """取得實時總覽數據"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求實時總覽數據")
        data = ga4_service.get_realtime_overview()
        logger.info(f"實時總覽查詢成功 - 用戶: {user_name}")
        
        return RealtimeOverviewResponse(
            user=user_name,
            data=data,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"實時總覽查詢失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"實時總覽查詢失敗: {str(e)}"
        )

@app.get("/realtime/top-pages", response_model=TopPagesResponse)
async def get_realtime_top_pages(limit: int = 10, x_api_key: Optional[str] = Header(None)):
    """取得實時熱門頁面"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求實時熱門頁面")
        pages = ga4_service.get_realtime_top_pages(limit=limit)
        logger.info(f"實時熱門頁面查詢成功 - 用戶: {user_name}, 頁面數: {len(pages)}")
        
        return TopPagesResponse(
            user=user_name,
            pages=pages,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"實時熱門頁面查詢失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"實時熱門頁面查詢失敗: {str(e)}"
        )

@app.get("/analytics/traffic-sources", response_model=TrafficSourcesResponse)
async def get_traffic_sources(
    start_date: str = "7daysAgo", 
    end_date: str = "today",
    x_api_key: Optional[str] = Header(None)
):
    """取得流量來源分析"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求流量來源分析")
        sources = ga4_service.get_traffic_sources(start_date=start_date, end_date=end_date)
        logger.info(f"流量來源分析成功 - 用戶: {user_name}, 來源數: {len(sources)}")
        
        return TrafficSourcesResponse(
            user=user_name,
            sources=sources,
            dateRange=f"{start_date} to {end_date}",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"流量來源分析失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"流量來源分析失敗: {str(e)}"
        )

@app.get("/analytics/pageviews", response_model=PageAnalyticsResponse)
async def get_pageviews_analytics(
    start_date: str = "7daysAgo", 
    end_date: str = "today",
    x_api_key: Optional[str] = Header(None)
):
    """取得頁面瀏覽分析"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求頁面瀏覽分析")
        analytics = ga4_service.get_pageviews_analytics(start_date=start_date, end_date=end_date)
        logger.info(f"頁面瀏覽分析成功 - 用戶: {user_name}")
        
        return PageAnalyticsResponse(
            user=user_name,
            analytics=analytics,
            dateRange=f"{start_date} to {end_date}",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"頁面瀏覽分析失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"頁面瀏覽分析失敗: {str(e)}"
        )

@app.get("/analytics/devices", response_model=DeviceAnalyticsResponse)
async def get_device_analytics(
    start_date: str = "7daysAgo", 
    end_date: str = "today",
    x_api_key: Optional[str] = Header(None)
):
    """取得設備分析數據"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求設備分析數據")
        devices = ga4_service.get_device_analytics(start_date=start_date, end_date=end_date)
        logger.info(f"設備分析成功 - 用戶: {user_name}, 設備數: {len(devices)}")
        
        return DeviceAnalyticsResponse(
            user=user_name,
            devices=devices,
            dateRange=f"{start_date} to {end_date}",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"設備分析失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"設備分析失敗: {str(e)}"
        )

@app.get("/analytics/geographic", response_model=GeographicDataResponse)
async def get_geographic_data(
    start_date: str = "7daysAgo", 
    end_date: str = "today",
    x_api_key: Optional[str] = Header(None)
):
    """取得地理位置數據"""
    user_name = verify_api_key(x_api_key)
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {user_name} 請求地理位置數據")
        locations = ga4_service.get_geographic_data(start_date=start_date, end_date=end_date)
        logger.info(f"地理位置數據查詢成功 - 用戶: {user_name}, 位置數: {len(locations)}")
        
        return GeographicDataResponse(
            user=user_name,
            locations=locations,
            dateRange=f"{start_date} to {end_date}",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"地理位置數據查詢失敗 - 用戶: {user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"地理位置數據查詢失敗: {str(e)}"
        )

# 錯誤處理
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 