import os
import json
from typing import Dict, Optional
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