import os
import json
from typing import Dict, Optional, List, Union
from datetime import datetime, timedelta
import logging
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, status, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunRealtimeReportRequest
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# V2 imports
from database import get_db, init_database, test_database_connection
from models import User, OAuthToken, ApiUsageLog, GoogleAnalyticsProperty
from oauth import oauth_handler, OAuthUserManager
from ga4_extensions import GA4DataService

# 載入環境變數
load_dotenv()

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 功能開關
ENABLE_OAUTH_MODE = os.getenv("ENABLE_OAUTH_MODE", "true").lower() == "true"
ENABLE_API_KEY_MODE = os.getenv("ENABLE_API_KEY_MODE", "true").lower() == "true"

# FastAPI 應用初始化
app = FastAPI(
    title="GA4 Realtime API Service V2",
    description="BlockTempo GA4 多租戶即時分析服務 - 支援 OAuth 和 API Key 雙模式",
    version="2.0.0"
)

# 自定義 OpenAPI schema，隱藏 OAuth 測試端點
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = {
        "openapi": "3.0.2",
        "info": {
            "title": "GA4 Analytics API Service",
            "version": "2.0.0",
            "description": """
## GA4 分析數據 API 服務

提供完整的 Google Analytics 4 數據查詢功能，支援即時數據和歷史分析。

### 認證方式
- **API Key**: 在請求頭中使用 `X-API-Key` 
- **OAuth 2.0**: 在請求頭中使用 `Authorization: Bearer {token}`

### 主要功能
- ✅ 即時在線人數查詢
- ✅ 實時總覽和熱門頁面
- ✅ 流量來源分析
- ✅ 頁面瀏覽統計
- ✅ 設備和地理位置分析
- ✅ 搜索詞和性能指標

### 使用說明
所有 API 端點都需要認證。請使用 API Key 或 OAuth token 進行身份驗證。
            """
        },
        "paths": {},
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API Key 認證"
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "OAuth 2.0 Bearer Token"
                }
            }
        },
        "security": [
            {"ApiKeyAuth": []},
            {"BearerAuth": []}
        ]
    }
    
    # 只包含 GA 數據查詢相關的端點
    allowed_paths = [
        "/",
        "/health", 
        "/active-users",
        "/realtime/overview",
        "/realtime/top-pages", 
        "/analytics/traffic-sources",
        "/analytics/pageviews",
        "/analytics/devices",
        "/analytics/geographic", 
        "/analytics/top-pages",
        "/analytics/search-terms",
        "/analytics/performance"
    ]
    
    # 獲取原始 schema
    from fastapi.openapi.utils import get_openapi
    original_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # 過濾路徑
    for path in allowed_paths:
        if path in original_schema["paths"]:
            openapi_schema["paths"][path] = original_schema["paths"][path]
    
    # 設置安全要求
    for path_info in openapi_schema["paths"].values():
        for method_info in path_info.values():
            if isinstance(method_info, dict) and "operationId" in method_info:
                method_info["security"] = [
                    {"ApiKeyAuth": []},
                    {"BearerAuth": []}
                ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 響應模型
class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str
    message: str

class OAuthCallbackResponse(BaseModel):
    message: str
    user_id: int
    email: str
    ga4_properties: List[Dict]

class UserInfoResponse(BaseModel):
    user_id: int
    email: str
    name: Optional[str]
    ga4_properties: List[Dict]
    created_at: str

class ActiveUsersResponse(BaseModel):
    user: str
    user_type: str  # "oauth" or "api_key"
    activeUsers: int
    property_id: str
    timestamp: str
    status: str = "success"

# V1 兼容性模型
class ActiveUsersResponseV1(BaseModel):
    user: str
    activeUsers: int
    timestamp: str
    status: str = "success"

# 配置和常量
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")

# V1 API Key 配置
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

API_KEYS = load_api_keys() if ENABLE_API_KEY_MODE else {}

# 速率限制
class RateLimiter:
    def __init__(self, max_requests: int = 200, time_window: int = 600):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        # 清理過期記錄
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.time_window
        ]
        
        # 檢查是否超過限制
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        # 記錄此次請求
        self.requests[identifier].append(now)
        return True

rate_limiter = RateLimiter()

# 初始化GA4數據服務
try:
    ga4_service = GA4DataService()
    logger.info("GA4DataService 初始化成功")
except Exception as e:
    logger.warning(f"GA4DataService 初始化失敗: {str(e)}")
    ga4_service = None

# 認證和用戶管理
class AuthenticationResult:
    def __init__(self, user_name: str, user_type: str, user_id: Optional[int] = None, 
                 ga4_property_id: Optional[str] = None, access_token: Optional[str] = None):
        self.user_name = user_name
        self.user_type = user_type  # "oauth" or "api_key"
        self.user_id = user_id
        self.ga4_property_id = ga4_property_id or GA4_PROPERTY_ID
        self.access_token = access_token

async def verify_authentication(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> AuthenticationResult:
    """統一認證處理：支援 OAuth Bearer Token 和 API Key"""
    
    # 記錄 API 使用
    async def log_api_usage(auth_result: AuthenticationResult, endpoint: str, status_code: int, 
                           response_time_ms: int = None, error_message: str = None):
        if db is None:
            # 無數據庫模式下跳過記錄
            return
        try:
            log_entry = ApiUsageLog(
                user_id=auth_result.user_id if auth_result.user_type == "oauth" else None,
                api_key_user=auth_result.user_name if auth_result.user_type == "api_key" else None,
                endpoint=endpoint,
                method=request.method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
                error_message=error_message
            )
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            logger.error(f"記錄 API 使用失敗: {e}")
    
    # 嘗試 OAuth 認證
    if authorization and authorization.startswith("Bearer ") and ENABLE_OAUTH_MODE and oauth_handler.enabled and db is not None:
        try:
            token = authorization.replace("Bearer ", "")
            
            # 查找用戶和 token
            from sqlalchemy import select
            
            result = await db.execute(
                select(User, OAuthToken).join(OAuthToken).where(
                    OAuthToken.access_token == token,
                    OAuthToken.is_revoked == False,
                    User.is_active == True
                )
            )
            user_token_pair = result.first()
            
            if not user_token_pair:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="無效的 OAuth token"
                )
            
            user, oauth_token = user_token_pair
            
            # 檢查 token 是否過期
            if oauth_token.is_expired:
                # 嘗試刷新 token
                new_access_token = await OAuthUserManager.refresh_user_token(
                    db, user.id, oauth_handler
                )
                if not new_access_token:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token 已過期，請重新授權"
                    )
                token = new_access_token
            
            # 速率限制檢查
            if not rate_limiter.is_allowed(f"oauth_{user.id}"):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="請求頻率過高，請稍後再試"
                )
            
            # 獲取用戶的 GA4 屬性
            result = await db.execute(
                select(GoogleAnalyticsProperty).where(
                    GoogleAnalyticsProperty.user_id == user.id,
                    GoogleAnalyticsProperty.is_active == True,
                    GoogleAnalyticsProperty.is_default == True
                )
            )
            default_property = result.scalar_one_or_none()
            
            if not default_property:
                # 如果沒有預設屬性，使用第一個活躍屬性
                result = await db.execute(
                    select(GoogleAnalyticsProperty).where(
                        GoogleAnalyticsProperty.user_id == user.id,
                        GoogleAnalyticsProperty.is_active == True
                    ).limit(1)
                )
                default_property = result.scalar_one_or_none()
            
            property_id = default_property.property_id if default_property else None
            
            logger.info(f"OAuth 認證成功 - 用戶: {user.email}")
            
            return AuthenticationResult(
                user_name=user.email,
                user_type="oauth",
                user_id=user.id,
                ga4_property_id=property_id,
                access_token=token
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OAuth 認證失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OAuth 認證處理失敗"
            )
    
    # 嘗試 API Key 認證
    elif x_api_key and ENABLE_API_KEY_MODE:
        # 首先檢查數據庫中的用戶 API Key
        if db is not None:
            try:
                from models import UserApiKey, GoogleAnalyticsProperty
                from sqlalchemy import select
                
                result = await db.execute(
                    select(UserApiKey, User, GoogleAnalyticsProperty).join(
                        User, UserApiKey.user_id == User.id
                    ).outerjoin(
                        GoogleAnalyticsProperty, 
                        UserApiKey.property_id == GoogleAnalyticsProperty.id
                    ).where(
                        UserApiKey.api_key == x_api_key,
                        UserApiKey.is_active == True,
                        User.is_active == True
                    ).limit(1)
                )
                
                user_api_key_result = result.first()
                
                if user_api_key_result:
                    user_api_key, user, property_obj = user_api_key_result
                    
                    # 速率限制檢查
                    if not rate_limiter.is_allowed(f"user_api_key_{user.id}"):
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="請求頻率過高，請稍後再試"
                        )
                    
                    # 更新最後使用時間
                    from datetime import datetime
                    user_api_key.last_used_at = datetime.utcnow()
                    await db.commit()
                    
                    property_id = property_obj.property_id if property_obj else None
                    
                    logger.info(f"用戶 API Key 認證成功 - 用戶: {user.email}")
                    
                    return AuthenticationResult(
                        user_name=user.email,
                        user_type="user_api_key",
                        user_id=user.id,
                        ga4_property_id=property_id,
                        access_token=None
                    )
                    
            except Exception as e:
                logger.error(f"用戶 API Key 檢查失敗: {e}")
        
        # 然後檢查靜態 API Key（.env 檔案中的）
        if x_api_key in API_KEYS:
            user_name = API_KEYS[x_api_key]
            
            # 速率限制檢查
            if not rate_limiter.is_allowed(f"api_key_{x_api_key}"):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="請求頻率過高，請稍後再試"
                )
            
            logger.info(f"靜態 API Key 認證成功 - 用戶: {user_name}")
            
            return AuthenticationResult(
                user_name=user_name,
                user_type="api_key",
                ga4_property_id=GA4_PROPERTY_ID
            )
        
        # 如果兩種 API Key 都不匹配
        logger.warning(f"無效的API Key嘗試: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的API Key"
        )
    
    # 沒有提供任何認證資訊
    else:
        missing_auth = []
        if ENABLE_OAUTH_MODE and oauth_handler.enabled:
            missing_auth.append("Authorization Bearer token")
        if ENABLE_API_KEY_MODE:
            missing_auth.append("X-API-Key header")
        
        if not missing_auth:
            # 如果沒有任何認證模式可用
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="服務未配置認證方式"
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"需要認證：{' 或 '.join(missing_auth)}"
        )

# GA4 客戶端管理
def get_ga4_client(auth_result: AuthenticationResult):
    """根據認證結果獲取對應的 GA4 客戶端"""
    try:
        if auth_result.user_type == "oauth":
            # OAuth 模式：使用用戶的 access token
            credentials = Credentials(token=auth_result.access_token)
            client = BetaAnalyticsDataClient(credentials=credentials)
        else:
            # API Key 模式：使用 Service Account
            if not SERVICE_ACCOUNT_JSON:
                raise ValueError("SERVICE_ACCOUNT_JSON 環境變數未設定")
            
            # 預處理 SERVICE_ACCOUNT_JSON - 修正控制字符問題
            processed_json = SERVICE_ACCOUNT_JSON.replace('\\n', '\\\\n').replace('\n', '\\n')
            
            credentials_info = json.loads(processed_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            client = BetaAnalyticsDataClient(credentials=credentials)
        
        logger.info(f"GA4客戶端初始化成功 - 模式: {auth_result.user_type}")
        return client
    
    except Exception as e:
        logger.error(f"GA4客戶端初始化失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4服務初始化失敗"
        )

# 應用啟動事件
@app.on_event("startup")
async def startup_event():
    """應用啟動時的初始化"""
    logger.info("🚀 GA4 API Service V2 啟動中...")
    
    # 初始化資料庫
    if ENABLE_OAUTH_MODE:
        try:
            await init_database()
            logger.info("✅ 資料庫初始化成功")
        except Exception as e:
            logger.error(f"❌ 資料庫初始化失敗: {e}")
    
    # 顯示啟用的模式
    enabled_modes = []
    if ENABLE_OAUTH_MODE and oauth_handler.enabled:
        enabled_modes.append("OAuth")
    elif ENABLE_OAUTH_MODE:
        enabled_modes.append("OAuth (配置不完整)")
    if ENABLE_API_KEY_MODE:
        enabled_modes.append("API Key")
    
    logger.info(f"🔐 啟用認證模式: {', '.join(enabled_modes)}")
    logger.info("✅ GA4 API Service V2 啟動完成")

# === 登錄介面 ===

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """顯示 OAuth 登錄介面"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GA4 API Service V2 - 登錄</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 400px;
            width: 90%;
            text-align: center;
        }
        
        .logo {
            font-size: 2rem;
            font-weight: bold;
            color: #333;
            margin-bottom: 8px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 32px;
            font-size: 14px;
        }
        
        .welcome-text {
            color: #444;
            margin-bottom: 32px;
            line-height: 1.5;
        }
        
        .login-button {
            background: #4285f4;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
            min-width: 200px;
        }
        
        .login-button:hover {
            background: #3367d6;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(66, 133, 244, 0.3);
        }
        
        .api-key-section {
            margin-top: 32px;
            padding-top: 32px;
            border-top: 1px solid #eee;
        }
        
        .api-key-title {
            font-size: 14px;
            color: #666;
            margin-bottom: 16px;
        }
        
        .api-demo-button {
            background: #34a853;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            transition: all 0.2s ease;
        }
        
        .api-demo-button:hover {
            background: #2e7d32;
            transform: translateY(-1px);
        }
        
        .features {
            margin-top: 24px;
            text-align: left;
            color: #666;
            font-size: 14px;
        }
        
        .feature-item {
            margin: 8px 0;
            display: flex;
            align-items: center;
        }
        
        .feature-icon {
            color: #4285f4;
            margin-right: 8px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">📊 GA4 API Service</div>
        <div class="subtitle">Version 2.0 - 多租戶分析平台</div>
        
        <div class="welcome-text">
            歡迎使用 GA4 API Service V2！<br>
            支援 OAuth 多租戶和 API Key 雙重認證模式
        </div>
        
        <a href="/auth/google" class="login-button">
            🔐 使用 Google 帳號登錄
        </a>
        
        <div class="features">
            <div class="feature-item">
                <span class="feature-icon">✓</span>
                個人專屬 GA4 數據存取
            </div>
            <div class="feature-item">
                <span class="feature-icon">✓</span>
                即時在線人數查詢
            </div>
            <div class="feature-item">
                <span class="feature-icon">✓</span>
                完整分析數據 API
            </div>
            <div class="feature-item">
                <span class="feature-icon">✓</span>
                安全的 OAuth 認證
            </div>
        </div>
        
        <div class="api-key-section">
            <div class="api-key-title">開發者測試模式</div>
            <a href="/docs" class="api-demo-button">
                📖 API 文檔與測試
            </a>
        </div>
    </div>
    
    <script>
        // 檢查 URL 參數中是否有錯誤或成功訊息
        const urlParams = new URLSearchParams(window.location.search);
        const error = urlParams.get('error');
        const success = urlParams.get('success');
        
        if (error) {
            alert('登錄失敗：' + decodeURIComponent(error));
        }
        
        if (success) {
            alert('登錄成功！' + decodeURIComponent(success));
        }
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

# === OAuth 相關端點 ===

@app.get("/auth/google")
async def google_oauth_init():
    """啟動 Google OAuth 授權流程 - 直接重定向到 Google"""
    if not ENABLE_OAUTH_MODE or not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth 模式未啟用或配置不完整"
        )
    
    try:
        auth_url, state = oauth_handler.build_auth_url()
        logger.info("重定向到 Google OAuth 授權頁面")
        
        # 直接重定向到 Google 授權頁面
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"生成 OAuth URL 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="無法啟動 OAuth 流程"
        )

@app.get("/auth/google/url", response_model=AuthUrlResponse)
async def get_google_oauth_url():
    """獲取 Google OAuth 授權 URL (API 格式)"""
    if not ENABLE_OAUTH_MODE or not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth 模式未啟用或配置不完整"
        )
    
    try:
        auth_url, state = oauth_handler.build_auth_url()
        logger.info("生成 Google OAuth 授權 URL")
        
        return AuthUrlResponse(
            auth_url=auth_url,
            state=state,
            message="請在瀏覽器中打開授權 URL 並完成授權"
        )
    except Exception as e:
        logger.error(f"生成 OAuth URL 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="無法啟動 OAuth 流程"
        )

@app.get("/auth/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """處理 Google OAuth 回調"""
    if not ENABLE_OAUTH_MODE or not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth 模式未啟用或配置不完整"
        )
    
    try:
        # 交換授權碼獲取 tokens
        tokens = await oauth_handler.exchange_code_for_tokens(code)
        
        # 獲取用戶資訊
        user_info = await oauth_handler.get_user_info(tokens["access_token"])
        
        # 獲取用戶的 GA4 屬性
        ga4_properties = oauth_handler.get_ga4_properties(tokens["access_token"])
        
        # 創建或更新用戶
        user = await OAuthUserManager.create_or_update_user(
            db, user_info, tokens, ga4_properties
        )
        
        logger.info(f"OAuth 授權成功 - 用戶: {user.email}")
        
        # 返回成功頁面
        property_count = len(ga4_properties) if ga4_properties else 0
        access_token = tokens.get("access_token", "")
        
        success_html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登錄成功 - GA4 API Service V2</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .success-container {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 500px;
            width: 90%;
            text-align: center;
        }}
        
        .success-icon {{
            font-size: 4rem;
            margin-bottom: 20px;
        }}
        
        .success-title {{
            font-size: 2rem;
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 16px;
        }}
        
        .user-info {{
            background: #f5f5f5;
            border-radius: 8px;
            padding: 20px;
            margin: 24px 0;
            text-align: left;
        }}
        
        .user-info h3 {{
            margin: 0 0 12px 0;
            color: #333;
            font-size: 1.1rem;
        }}
        
        .info-item {{
            margin: 8px 0;
            color: #666;
        }}
        
        .info-label {{
            font-weight: 600;
            color: #444;
        }}
        
        .action-buttons {{
            margin-top: 32px;
        }}
        
        .btn {{
            background: #4285f4;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
            margin: 8px;
        }}
        
        .btn:hover {{
            background: #3367d6;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(66, 133, 244, 0.3);
        }}
        
        .btn-secondary {{
            background: #34a853;
        }}
        
        .btn-secondary:hover {{
            background: #2e7d32;
        }}
        
        .next-steps {{
            margin-top: 24px;
            text-align: left;
            color: #666;
        }}
        
        .step-item {{
            margin: 12px 0;
            padding-left: 24px;
            position: relative;
        }}
        
        .step-item::before {{
            content: "▶";
            position: absolute;
            left: 0;
            color: #4285f4;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="success-container">
        <div class="success-icon">🎉</div>
        <div class="success-title">登錄成功！</div>
        
        <div class="user-info">
            <h3>🔐 帳戶資訊</h3>
            <div class="info-item">
                <span class="info-label">用戶 ID:</span> {user.id}
            </div>
            <div class="info-item">
                <span class="info-label">電子郵件:</span> {user.email}
            </div>
            <div class="info-item">
                <span class="info-label">GA4 屬性:</span> {property_count} 個
            </div>
            <div class="info-item">
                <span class="info-label">狀態:</span> 已啟用
            </div>
        </div>
        
        <div class="next-steps">
            <h3>📋 接下來您可以：</h3>
            <div class="step-item">使用 API 文檔測試 OAuth 端點</div>
            <div class="step-item">查看您的個人 GA4 數據</div>
            <div class="step-item">整合到您的應用程式中</div>
        </div>
        
        <div class="action-buttons">
            <a href="/dashboard" class="btn btn-secondary">📊 用戶儀表板</a>
            <a href="/user/info" class="btn">👤 查看用戶資訊</a>
        </div>
    </div>
    
    <script>
        // 儲存 access token 到 localStorage
        const accessToken = '{access_token}';
        
        if (accessToken) {{
            localStorage.setItem("access_token", accessToken);
            console.log("Access token 已儲存到 localStorage");
        }}
        
        // 3秒後自動跳轉到用戶儀表板
        setTimeout(() => {{
            document.querySelector(".action-buttons").innerHTML += 
                '<div style="margin-top: 16px; color: #666; font-size: 14px;">將在 3 秒後自動跳轉到用戶儀表板...</div>';
        }}, 2000);
        
        setTimeout(() => {{
            window.location.href = "/dashboard";
        }}, 5000);
    </script>
</body>
</html>
"""
        
        return HTMLResponse(content=success_html)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth 回調處理失敗: {e}")
        # 返回錯誤頁面
        error_html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登錄失敗 - GA4 API Service V2</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .error-container {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 400px;
            width: 90%;
            text-align: center;
        }}
        
        .error-icon {{
            font-size: 4rem;
            margin-bottom: 20px;
        }}
        
        .error-title {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #d32f2f;
            margin-bottom: 16px;
        }}
        
        .error-message {{
            color: #666;
            margin-bottom: 24px;
            line-height: 1.5;
        }}
        
        .btn {{
            background: #4285f4;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
        }}
        
        .btn:hover {{
            background: #3367d6;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(66, 133, 244, 0.3);
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">❌</div>
        <div class="error-title">登錄失敗</div>
        <div class="error-message">
            OAuth 授權過程中發生錯誤，請重試。<br>
            錯誤詳情：{str(e)}
        </div>
        <a href="/login" class="btn">🔄 重新嘗試</a>
    </div>
</body>
</html>
        """
        return HTMLResponse(content=error_html, status_code=400)

@app.get("/auth/callback/json", response_model=OAuthCallbackResponse)
async def google_oauth_callback_json(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """處理 Google OAuth 回調 (JSON API 格式)"""
    if not ENABLE_OAUTH_MODE or not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OAuth 模式未啟用或配置不完整"
        )
    
    try:
        # 交換授權碼獲取 tokens
        tokens = await oauth_handler.exchange_code_for_tokens(code)
        
        # 獲取用戶資訊
        user_info = await oauth_handler.get_user_info(tokens["access_token"])
        
        # 獲取用戶的 GA4 屬性
        ga4_properties = oauth_handler.get_ga4_properties(tokens["access_token"])
        
        # 創建或更新用戶
        user = await OAuthUserManager.create_or_update_user(
            db, user_info, tokens, ga4_properties
        )
        
        logger.info(f"OAuth 授權成功 (JSON API) - 用戶: {user.email}")
        
        return OAuthCallbackResponse(
            message="授權成功",
            user_id=user.id,
            email=user.email,
            ga4_properties=[
                {"property_id": prop.get("property_id"), "name": prop.get("display_name")}
                for prop in ga4_properties
            ]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth 回調處理失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth 授權失敗"
        )

@app.get("/user/info", response_model=UserInfoResponse)
async def get_user_info(
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """獲取當前用戶資訊"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此端點僅支援 OAuth 用戶"
        )
    
    try:
        from sqlalchemy import select
        
        # 獲取用戶資訊
        result = await db.execute(select(User).where(User.id == auth.user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用戶不存在"
            )
        
        # 獲取用戶的 GA4 屬性
        from models import GoogleAnalyticsProperty
        result = await db.execute(
            select(GoogleAnalyticsProperty).where(
                GoogleAnalyticsProperty.user_id == user.id,
                GoogleAnalyticsProperty.is_active == True
            )
        )
        properties = result.scalars().all()
        
        return UserInfoResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            ga4_properties=[
                {
                    "property_id": prop.property_id,
                    "name": prop.property_name,
                    "is_default": prop.is_default
                }
                for prop in properties
            ],
            created_at=user.created_at.isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取用戶資訊失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="無法獲取用戶資訊"
        )

# === 主要 API 端點 ===

@app.get("/", response_model=dict)
async def root():
    """健康檢查端點"""
    return {
        "service": "GA4 Realtime API Service V2",
        "status": "running",
        "version": "2.0.0",
        "features": {
            "oauth_mode": ENABLE_OAUTH_MODE and oauth_handler.enabled,
            "api_key_mode": ENABLE_API_KEY_MODE
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health", response_model=dict)
async def health_check():
    """詳細健康檢查"""
    checks = {
        "api_service": "ok",
        "ga4_property_configured": bool(GA4_PROPERTY_ID),
        "service_account_configured": bool(SERVICE_ACCOUNT_JSON),
        "oauth_configured": ENABLE_OAUTH_MODE and oauth_handler.enabled,
        "api_keys_loaded": len(API_KEYS) > 0 if ENABLE_API_KEY_MODE else False,
        "database_available": False
    }
    
    # 測試資料庫連接
    if ENABLE_OAUTH_MODE:
        try:
            checks["database_available"] = await test_database_connection()
        except:
            checks["database_available"] = False
    
    all_ok = all(checks.values())
    
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "enabled_modes": {
            "oauth": ENABLE_OAUTH_MODE,
            "api_key": ENABLE_API_KEY_MODE
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/active-users")
async def get_active_users(
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得GA4即時在線人數 - 支援雙模式認證"""
    
    try:
        # 檢查必要配置
        if not auth.ga4_property_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GA4 Property ID 未配置"
            )
        
        # 初始化GA4客戶端
        client = get_ga4_client(auth)
        
        # 建立請求
        request = RunRealtimeReportRequest(
            property=f"properties/{auth.ga4_property_id}",
            metrics=[{"name": "activeUsers"}]
        )
        
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求GA4數據")
        
        # 執行請求
        response = client.run_realtime_report(request=request)
        
        # 解析響應
        active_users = 0
        if response.rows:
            active_users = int(response.rows[0].metric_values[0].value)
        
        logger.info(f"GA4查詢成功 - 用戶: {auth.user_name}, 在線人數: {active_users}")
        
        # 根據用戶類型返回不同格式的響應
        if auth.user_type == "api_key":
            # V1 兼容格式
            return ActiveUsersResponseV1(
                user=auth.user_name,
                activeUsers=active_users,
                timestamp=datetime.now().isoformat()
            )
        else:
            # V2 完整格式
            return ActiveUsersResponse(
                user=auth.user_name,
                user_type=auth.user_type,
                activeUsers=active_users,
                property_id=auth.ga4_property_id,
                timestamp=datetime.now().isoformat()
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GA4查詢失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GA4查詢失敗: {str(e)}"
        )

# === GA4 分析端點 ===

@app.get("/realtime/overview")
async def get_realtime_overview(
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得實時總覽數據"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求實時總覽數據")
        data = ga4_service.get_realtime_overview()
        logger.info(f"實時總覽查詢成功 - 用戶: {auth.user_name}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "data": data,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "data": data,
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"實時總覽查詢失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"實時總覽查詢失敗: {str(e)}"
        )

@app.get("/realtime/top-pages")
async def get_realtime_top_pages(
    limit: int = 10,
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得實時熱門頁面"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求實時熱門頁面")
        pages = ga4_service.get_realtime_top_pages(limit=limit)
        logger.info(f"實時熱門頁面查詢成功 - 用戶: {auth.user_name}, 頁面數: {len(pages)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "pages": pages,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "pages": pages,
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"實時熱門頁面查詢失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"實時熱門頁面查詢失敗: {str(e)}"
        )

@app.get("/analytics/traffic-sources")
async def get_traffic_sources(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得流量來源分析"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求流量來源分析")
        sources = ga4_service.get_traffic_sources(start_date=start_date, end_date=end_date)
        logger.info(f"流量來源分析成功 - 用戶: {auth.user_name}, 來源數: {len(sources)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "sources": sources,
                "dateRange": f"{start_date} to {end_date}",
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "sources": sources,
                "dateRange": f"{start_date} to {end_date}",
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"流量來源分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"流量來源分析失敗: {str(e)}"
        )

@app.get("/analytics/pageviews")
async def get_pageviews_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得頁面瀏覽分析"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求頁面瀏覽分析")
        analytics = ga4_service.get_pageviews_analytics(start_date=start_date, end_date=end_date)
        logger.info(f"頁面瀏覽分析成功 - 用戶: {auth.user_name}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "analytics": analytics,
                "dateRange": f"{start_date} to {end_date}",
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "analytics": analytics,
                "dateRange": f"{start_date} to {end_date}",
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"頁面瀏覽分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"頁面瀏覽分析失敗: {str(e)}"
        )

@app.get("/analytics/devices")
async def get_device_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得設備分析數據"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求設備分析數據")
        devices = ga4_service.get_device_analytics(start_date=start_date, end_date=end_date)
        logger.info(f"設備分析成功 - 用戶: {auth.user_name}, 設備數: {len(devices)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "devices": devices,
                "dateRange": f"{start_date} to {end_date}",
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "devices": devices,
                "dateRange": f"{start_date} to {end_date}",
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"設備分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"設備分析失敗: {str(e)}"
        )

@app.get("/analytics/geographic")
async def get_geographic_data(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得地理位置數據"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求地理位置數據")
        locations = ga4_service.get_geographic_data(start_date=start_date, end_date=end_date)
        logger.info(f"地理位置數據查詢成功 - 用戶: {auth.user_name}, 位置數: {len(locations)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "locations": locations,
                "dateRange": f"{start_date} to {end_date}",
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "locations": locations,
                "dateRange": f"{start_date} to {end_date}",
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"地理位置數據查詢失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"地理位置數據查詢失敗: {str(e)}"
        )

@app.get("/analytics/top-pages")
async def get_top_pages_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得熱門頁面分析"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求熱門頁面分析")
        pages = ga4_service.get_top_pages_analytics(start_date=start_date, end_date=end_date, limit=limit)
        logger.info(f"熱門頁面分析成功 - 用戶: {auth.user_name}, 頁面數: {len(pages)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "pages": pages,
                "dateRange": f"{start_date} to {end_date}",
                "totalPages": len(pages),
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "pages": pages,
                "dateRange": f"{start_date} to {end_date}",
                "totalPages": len(pages),
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"熱門頁面分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"熱門頁面分析失敗: {str(e)}"
        )

@app.get("/analytics/search-terms")
async def get_search_terms(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得搜索詞分析"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求搜索詞分析")
        search_terms = ga4_service.get_search_terms(start_date=start_date, end_date=end_date, limit=limit)
        logger.info(f"搜索詞分析成功 - 用戶: {auth.user_name}, 詞數: {len(search_terms)}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "searchTerms": search_terms,
                "dateRange": f"{start_date} to {end_date}",
                "totalTerms": len(search_terms),
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "searchTerms": search_terms,
                "dateRange": f"{start_date} to {end_date}",
                "totalTerms": len(search_terms),
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"搜索詞分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索詞分析失敗: {str(e)}"
        )

@app.get("/analytics/performance")
async def get_performance_metrics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_authentication)
):
    """取得性能指標分析"""
    
    if not ga4_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GA4DataService 未初始化"
        )
    
    try:
        logger.info(f"用戶 {auth.user_name} ({auth.user_type}) 請求性能指標分析")
        performance = ga4_service.get_performance_metrics(start_date=start_date, end_date=end_date, limit=limit)
        logger.info(f"性能指標分析成功 - 用戶: {auth.user_name}")
        
        if auth.user_type == "api_key":
            # V1 兼容格式
            return {
                "user": auth.user_name,
                "performance": performance,
                "dateRange": f"{start_date} to {end_date}",
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        else:
            # V2 完整格式
            return {
                "user": auth.user_name,
                "user_type": auth.user_type,
                "performance": performance,
                "dateRange": f"{start_date} to {end_date}",
                "property_id": auth.ga4_property_id,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"性能指標分析失敗 - 用戶: {auth.user_name}, 錯誤: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"性能指標分析失敗: {str(e)}"
        )

# 錯誤處理
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """統一錯誤處理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url)
        }
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard():
    """用戶管理儀表板"""
    dashboard_html = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>用戶儀表板 - GA4 API Service V2</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }
        
        .dashboard-container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 30px;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 30px;
            margin-bottom: 20px;
        }
        
        .card-title {
            font-size: 1.5rem;
            font-weight: bold;
            color: #333;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .user-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .info-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #4285f4;
        }
        
        .info-label {
            font-weight: 600;
            color: #666;
            font-size: 0.9rem;
        }
        
        .info-value {
            font-size: 1.1rem;
            color: #333;
            margin-top: 5px;
        }
        
        .btn {
            background: #4285f4;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
            margin: 8px;
        }
        
        .btn:hover {
            background: #3367d6;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(66, 133, 244, 0.3);
        }
        
        .btn-success {
            background: #34a853;
        }
        
        .btn-success:hover {
            background: #2e7d32;
        }
        
        .btn-danger {
            background: #ea4335;
        }
        
        .btn-danger:hover {
            background: #c5221f;
        }
        
        .api-key-item {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            display: flex;
            justify-content: between;
            align-items: center;
        }
        
        .api-key-info {
            flex: 1;
        }
        
        .api-key-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }
        
        .api-key-value {
            font-family: monospace;
            background: #e9ecef;
            padding: 8px 12px;
            border-radius: 4px;
            margin: 10px 0;
            word-break: break-all;
        }
        
        .api-key-actions {
            display: flex;
            gap: 10px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        
        .form-input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            box-sizing: border-box;
        }
        
        .form-input:focus {
            outline: none;
            border-color: #4285f4;
            box-shadow: 0 0 0 3px rgba(66, 133, 244, 0.1);
        }
        
        .property-item {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }
        
        .property-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }
        
        .property-id {
            font-family: monospace;
            color: #666;
            margin-bottom: 10px;
        }
        
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        .status-active {
            background: #d4edda;
            color: #155724;
        }
        
        .status-inactive {
            background: #f8d7da;
            color: #721c24;
        }
        
        .loading {
            text-align: center;
            color: #666;
            font-style: italic;
        }
        
        .error {
            color: #ea4335;
            background: #fef2f2;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border: 1px solid #fed7d7;
        }
        
        .success {
            color: #2e7d32;
            background: #f1f8e9;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border: 1px solid #c8e6c9;
        }
        
        .tabs {
            display: flex;
            border-bottom: 2px solid #e9ecef;
            margin-bottom: 20px;
        }
        
        .tab-button {
            background: none;
            border: none;
            padding: 15px 25px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            color: #666;
            border-bottom: 3px solid transparent;
            transition: all 0.2s ease;
        }
        
        .tab-button.active {
            color: #4285f4;
            border-bottom-color: #4285f4;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="dashboard-container">
        <!-- 頭部 -->
        <div class="header">
            <h1>🚀 GA4 API 用戶儀表板</h1>
            <p>管理您的 API Keys 和 Google Analytics 屬性</p>
            <div id="user-info" class="loading">載入用戶資訊中...</div>
        </div>
        
        <!-- 頁籤 -->
        <div class="card">
            <div class="tabs">
                <button class="tab-button active" onclick="showTab('overview')">📊 總覽</button>
                <button class="tab-button" onclick="showTab('api-keys')">🔑 API Keys</button>
                <button class="tab-button" onclick="showTab('properties')">📈 GA4 屬性</button>
                <button class="tab-button" onclick="showTab('usage')">📋 使用記錄</button>
            </div>
            
            <!-- 總覽頁籤 -->
            <div id="overview-tab" class="tab-content active">
                <h2 class="card-title">📊 帳戶總覽</h2>
                <div class="user-info" id="overview-stats">
                    <div class="info-item">
                        <div class="info-label">API Keys 數量</div>
                        <div class="info-value" id="api-keys-count">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">GA4 屬性數量</div>
                        <div class="info-value" id="properties-count">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">本月 API 調用</div>
                        <div class="info-value" id="monthly-calls">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">帳戶狀態</div>
                        <div class="info-value">✅ 正常</div>
                    </div>
                </div>
                
                <h3>🚀 快速開始</h3>
                <p>選擇一個操作來開始使用：</p>
                <button class="btn btn-success" onclick="showTab('api-keys')">🔑 創建 API Key</button>
                <button class="btn" onclick="showTab('properties')">📈 添加 GA4 屬性</button>
                <a href="/docs" class="btn" target="_blank">📖 API 文檔</a>
            </div>
            
            <!-- API Keys 管理頁籤 -->
            <div id="api-keys-tab" class="tab-content">
                <h2 class="card-title">🔑 API Keys 管理</h2>
                
                <!-- 創建新 API Key -->
                <div style="margin-bottom: 30px;">
                    <h3>創建新 API Key</h3>
                    <div class="form-group">
                        <label class="form-label">API Key 名稱</label>
                        <input type="text" class="form-input" id="new-api-key-name" placeholder="例如：我的專案 API Key">
                    </div>
                    <div class="form-group">
                        <label class="form-label">描述 (可選)</label>
                        <input type="text" class="form-input" id="new-api-key-description" placeholder="這個 API Key 的用途說明">
                    </div>
                    <div class="form-group">
                        <label class="form-label">綁定 GA4 屬性 (可選)</label>
                        <select class="form-input" id="new-api-key-property" style="cursor: pointer;">
                            <option value="">請選擇 GA4 屬性（可留空使用預設）</option>
                        </select>
                        <small style="color: #666; font-size: 12px;">
                            如果選擇特定屬性，此 API Key 只能查詢該屬性的數據
                        </small>
                    </div>
                    <button class="btn btn-success" onclick="createApiKey()">創建 API Key</button>
                </div>
                
                <!-- 現有 API Keys -->
                <h3>您的 API Keys</h3>
                <div id="api-keys-list" class="loading">載入中...</div>
            </div>
            
            <!-- GA4 屬性管理頁籤 -->
            <div id="properties-tab" class="tab-content">
                <h2 class="card-title">📈 GA4 屬性管理</h2>
                
                <!-- 添加新屬性 -->
                <div style="margin-bottom: 30px;">
                    <h3>添加 GA4 屬性</h3>
                    <div class="form-group">
                        <label class="form-label">GA4 屬性 ID</label>
                        <input type="text" class="form-input" id="new-property-id" placeholder="例如：123456789">
                    </div>
                    <div class="form-group">
                        <label class="form-label">屬性名稱</label>
                        <input type="text" class="form-input" id="new-property-name" placeholder="例如：我的網站">
                    </div>
                    <button class="btn btn-success" onclick="addProperty()">添加屬性</button>
                </div>
                
                <!-- 現有屬性 -->
                <h3>您的 GA4 屬性</h3>
                <div id="properties-list" class="loading">載入中...</div>
            </div>
            
            <!-- 使用記錄頁籤 -->
            <div id="usage-tab" class="tab-content">
                <h2 class="card-title">📋 API 使用記錄</h2>
                <div id="usage-stats" class="loading">載入中...</div>
            </div>
        </div>
    </div>
    
    <script>
        // 全局變數
        let accessToken = localStorage.getItem("access_token");
        let userInfo = null;
        
        // 頁籤切換
        function showTab(tabName) {
            // 隱藏所有頁籤內容
            document.querySelectorAll(".tab-content").forEach(content => {
                content.classList.remove("active");
            });
            
            // 移除所有頁籤按鈕的 active 狀態
            document.querySelectorAll(".tab-button").forEach(button => {
                button.classList.remove("active");
            });
            
            // 顯示選中的頁籤
            document.getElementById(tabName + "-tab").classList.add("active");
            event.target.classList.add("active");
            
            // 載入對應的數據
            if (tabName === "api-keys") {
                loadApiKeys();
                loadPropertiesForApiKey(); // 載入屬性選項
            } else if (tabName === "properties") {
                loadProperties();
            } else if (tabName === "usage") {
                loadUsageStats();
            }
        }
        
        // 初始化載入
        async function init() {
            if (!accessToken) {
                document.getElementById("user-info").innerHTML = 
                    '<div class="error">❌ 未登入或 Token 過期，請重新登入</div><a href="/login" class="btn">重新登入</a>';
                return;
            }
            
            try {
                await loadUserInfo();
                await loadOverviewStats();
            } catch (error) {
                console.error("初始化失敗:", error);
                document.getElementById("user-info").innerHTML = 
                    '<div class="error">❌ 載入失敗，請重新登入</div><a href="/login" class="btn">重新登入</a>';
            }
        }
        
        // 載入用戶資訊
        async function loadUserInfo() {
            try {
                const response = await fetch("/user/info", {
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                if (!response.ok) {
                    throw new Error("用戶資訊載入失敗");
                }
                
                userInfo = await response.json();
                document.getElementById("user-info").innerHTML = `
                    <div style="text-align: left;">
                        <strong>👤 ${userInfo.name || userInfo.email}</strong><br>
                        <span style="color: #666;">${userInfo.email}</span><br>
                        <span style="color: #666;">加入時間: ${new Date(userInfo.created_at).toLocaleDateString()}</span>
                    </div>
                `;
            } catch (error) {
                throw error;
            }
        }
        
        // 載入總覽統計
        async function loadOverviewStats() {
            // 這裡可以添加載入統計數據的邏輯
            document.getElementById("api-keys-count").textContent = "0";
            document.getElementById("properties-count").textContent = userInfo.ga4_properties?.length || 0;
            document.getElementById("monthly-calls").textContent = "0";
        }
        
        // 載入 API Keys
        async function loadApiKeys() {
            document.getElementById("api-keys-list").innerHTML = '<div class="loading">載入中...</div>';
            
            try {
                const response = await fetch("/api/user/api-keys", {
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                if (!response.ok) {
                    throw new Error("載入 API Keys 失敗");
                }
                
                const data = await response.json();
                
                if (data.api_keys && data.api_keys.length > 0) {
                    let html = "";
                    data.api_keys.forEach(key => {
                        let propertyInfo = "";
                        if (key.property) {
                            propertyInfo = `<div style="margin: 5px 0; padding: 4px 8px; background: #e3f2fd; color: #1976d2; border-radius: 4px; font-size: 12px; display: inline-block;">📈 ${key.property.property_name} (${key.property.property_id})</div>`;
                        } else {
                            propertyInfo = `<div style="margin: 5px 0; padding: 4px 8px; background: #fff3e0; color: #f57c00; border-radius: 4px; font-size: 12px; display: inline-block;">🔄 使用預設屬性</div>`;
                        }
                        
                        html += `
                            <div class="api-key-item" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e9ecef;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <h4 style="margin: 0 0 5px 0; color: #2c3e50;">${key.name}</h4>
                                        <p style="margin: 0 0 10px 0; color: #666; font-size: 14px;">${key.description || '無描述'}</p>
                                        ${propertyInfo}
                                        <div style="font-family: monospace; background: #fff; padding: 8px; border-radius: 4px; border: 1px solid #ddd; font-size: 12px; color: #333; word-break: break-all; margin: 8px 0;">${key.api_key}</div>
                                        <small style="color: #888;">創建時間: ${new Date(key.created_at).toLocaleString()}</small>
                                        ${key.last_used_at ? `<br><small style="color: #888;">最後使用: ${new Date(key.last_used_at).toLocaleString()}</small>` : ''}
                                    </div>
                                    <div>
                                        <button class="btn" style="background: #dc3545; color: white; font-size: 12px; padding: 5px 10px;" onclick="deleteApiKey(${key.id})">刪除</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    document.getElementById("api-keys-list").innerHTML = html;
                    
                    // 更新總覽統計
                    document.getElementById("api-keys-count").textContent = data.api_keys.length;
                } else {
                    document.getElementById("api-keys-list").innerHTML = `
                        <div class="info-item">
                            <div class="info-value" style="text-align: center; color: #666;">
                                📋 您還沒有創建任何 API Key<br>
                                <small>點擊上方的「創建 API Key」按鈕來開始</small>
                            </div>
                        </div>
                    `;
                    document.getElementById("api-keys-count").textContent = "0";
                }
            } catch (error) {
                console.error("載入 API Keys 失敗:", error);
                document.getElementById("api-keys-list").innerHTML = `
                    <div class="error">載入 API Keys 失敗: ${error.message}</div>
                `;
            }
        }
        
        // 載入 GA4 屬性
        async function loadProperties() {
            document.getElementById("properties-list").innerHTML = '<div class="loading">載入中...</div>';
            
            try {
                const response = await fetch("/api/user/properties", {
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                if (!response.ok) {
                    throw new Error("載入 GA4 屬性失敗");
                }
                
                const data = await response.json();
                
                if (data.properties && data.properties.length > 0) {
                    let html = "";
                    data.properties.forEach(prop => {
                        html += `
                            <div class="property-item" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e9ecef;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <h4 style="margin: 0 0 5px 0; color: #2c3e50;">${prop.property_name}</h4>
                                        <div style="font-family: monospace; color: #666; font-size: 14px;">Property ID: ${prop.property_id}</div>
                                        <span class="status-badge" style="background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-top: 5px; display: inline-block;">✅ 已連接</span>
                                        ${prop.is_default ? '<span class="status-badge" style="background: #e3f2fd; color: #1976d2; margin-left: 10px; padding: 2px 8px; border-radius: 12px; font-size: 12px;">🌟 預設</span>' : ''}
                                        <br><small style="color: #888;">添加時間: ${new Date(prop.created_at).toLocaleString()}</small>
                                    </div>
                                    <div>
                                        <button class="btn" style="background: #dc3545; color: white; font-size: 12px; padding: 5px 10px;" onclick="deleteProperty(${prop.id})">移除</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    document.getElementById("properties-list").innerHTML = html;
                    
                    // 更新總覽統計
                    document.getElementById("properties-count").textContent = data.properties.length;
                } else {
                    document.getElementById("properties-list").innerHTML = `
                        <div class="info-item">
                            <div class="info-value" style="text-align: center; color: #666;">
                                📈 您還沒有添加任何 GA4 屬性<br>
                                <small>添加 GA4 屬性來開始使用 API 服務</small>
                            </div>
                        </div>
                    `;
                    document.getElementById("properties-count").textContent = "0";
                }
            } catch (error) {
                console.error("載入 GA4 屬性失敗:", error);
                document.getElementById("properties-list").innerHTML = `
                    <div class="error">載入 GA4 屬性失敗: ${error.message}</div>
                `;
            }
        }
        
        // 載入使用統計
        async function loadUsageStats() {
            document.getElementById("usage-stats").innerHTML = `
                <div class="info-item">
                    <div class="info-value" style="text-align: center; color: #666;">
                        📊 使用統計功能開發中<br>
                        <small>很快就會上線，敬請期待！</small>
                    </div>
                </div>
            `;
        }
        
        // 載入 GA4 屬性選項（用於 API Key 創建）
        async function loadPropertiesForApiKey() {
            try {
                const response = await fetch("/api/user/properties", {
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    const select = document.getElementById("new-api-key-property");
                    
                    // 清空現有選項（保留第一個預設選項）
                    select.innerHTML = '<option value="">請選擇 GA4 屬性（可留空使用預設）</option>';
                    
                    // 添加用戶的 GA4 屬性
                    if (data.properties && data.properties.length > 0) {
                        data.properties.forEach(prop => {
                            const option = document.createElement("option");
                            option.value = prop.id;
                            option.textContent = `${prop.property_name} (${prop.property_id})`;
                            select.appendChild(option);
                        });
                    }
                }
            } catch (error) {
                console.error("載入 GA4 屬性選項失敗:", error);
            }
        }
        
        // 創建 API Key
        async function createApiKey() {
            const name = document.getElementById("new-api-key-name").value;
            const description = document.getElementById("new-api-key-description").value;
            const propertyId = document.getElementById("new-api-key-property").value;
            
            if (!name.trim()) {
                alert("請輸入 API Key 名稱");
                return;
            }
            
            try {
                const requestBody = {
                    name: name.trim(),
                    description: description.trim()
                };
                
                // 如果選擇了 GA4 屬性，添加到請求中
                if (propertyId) {
                    requestBody.property_id = parseInt(propertyId);
                }
                
                const response = await fetch("/api/user/api-keys", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + accessToken
                    },
                    body: JSON.stringify(requestBody)
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    let message = `✅ API Key 創建成功！\\n\\n名稱: ${data.api_key.name}\\n\\nAPI Key:\\n${data.api_key.api_key}`;
                    
                    if (data.api_key.property) {
                        message += `\\n\\n綁定屬性: ${data.api_key.property.property_name} (${data.api_key.property.property_id})`;
                    } else {
                        message += `\\n\\n綁定屬性: 無 (使用用戶預設屬性)`;
                    }
                    
                    message += `\\n\\n請妥善保存此 API Key，刷新頁面後將無法再次查看完整內容。`;
                    
                    alert(message);
                    
                    // 清空表單
                    document.getElementById("new-api-key-name").value = "";
                    document.getElementById("new-api-key-description").value = "";
                    document.getElementById("new-api-key-property").selectedIndex = 0;
                    
                    // 重新載入 API Keys 列表
                    loadApiKeys();
                } else {
                    throw new Error(data.detail || "創建 API Key 失敗");
                }
                
            } catch (error) {
                console.error("創建 API Key 失敗:", error);
                alert(`❌ 創建 API Key 失敗: ${error.message}`);
            }
        }
        
        // 添加 GA4 屬性
        async function addProperty() {
            const propertyId = document.getElementById("new-property-id").value;
            const propertyName = document.getElementById("new-property-name").value;
            
            if (!propertyId.trim()) {
                alert("請輸入 GA4 屬性 ID");
                return;
            }
            
            if (!propertyName.trim()) {
                alert("請輸入屬性名稱");
                return;
            }
            
            try {
                const response = await fetch("/api/user/properties", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + accessToken
                    },
                    body: JSON.stringify({
                        property_id: propertyId.trim(),
                        property_name: propertyName.trim()
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    alert(`✅ GA4 屬性添加成功！\\n\\n屬性名稱: ${data.property.property_name}\\n屬性 ID: ${data.property.property_id}`);
                    
                    // 清空表單
                    document.getElementById("new-property-id").value = "";
                    document.getElementById("new-property-name").value = "";
                    
                    // 重新載入屬性列表
                    loadProperties();
                } else {
                    throw new Error(data.detail || "添加 GA4 屬性失敗");
                }
                
            } catch (error) {
                console.error("添加 GA4 屬性失敗:", error);
                alert(`❌ 添加 GA4 屬性失敗: ${error.message}`);
            }
        }
        
        // 刪除 API Key
        async function deleteApiKey(keyId) {
            if (!confirm("確定要刪除這個 API Key 嗎？此操作無法撤銷。")) {
                return;
            }
            
            try {
                const response = await fetch(`/api/user/api-keys/${keyId}`, {
                    method: "DELETE",
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    alert("✅ API Key 已成功刪除");
                    loadApiKeys(); // 重新載入列表
                } else {
                    throw new Error(data.detail || "刪除 API Key 失敗");
                }
                
            } catch (error) {
                console.error("刪除 API Key 失敗:", error);
                alert(`❌ 刪除 API Key 失敗: ${error.message}`);
            }
        }
        
        // 刪除 GA4 屬性
        async function deleteProperty(propertyId) {
            if (!confirm("確定要移除這個 GA4 屬性嗎？此操作無法撤銷。")) {
                return;
            }
            
            try {
                const response = await fetch(`/api/user/properties/${propertyId}`, {
                    method: "DELETE",
                    headers: {
                        "Authorization": "Bearer " + accessToken
                    }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    alert("✅ GA4 屬性已成功移除");
                    loadProperties(); // 重新載入列表
                } else {
                    throw new Error(data.detail || "移除 GA4 屬性失敗");
                }
                
            } catch (error) {
                console.error("移除 GA4 屬性失敗:", error);
                alert(`❌ 移除 GA4 屬性失敗: ${error.message}`);
            }
        }
        
        // 頁面載入時初始化
        document.addEventListener("DOMContentLoaded", init);
    </script>
</body>
</html>
    """
    
    return HTMLResponse(content=dashboard_html)

# === API Key 管理 API 端點 ===

@app.post("/api/user/api-keys")
async def create_user_api_key(
    request: dict,
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """創建用戶專屬 API Key"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import UserApiKey
        import secrets
        import string
        
        # 驗證輸入
        key_name = request.get("name", "").strip()
        description = request.get("description", "").strip()
        property_id = request.get("property_id")  # GA4 屬性 ID（可選）
        
        if not key_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API Key 名稱不能為空"
            )
        
        if len(key_name) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API Key 名稱過長（最多100字符）"
            )
        
        # 驗證 GA4 屬性（如果提供）
        property_obj = None
        if property_id:
            from models import GoogleAnalyticsProperty
            result = await db.execute(
                select(GoogleAnalyticsProperty).where(
                    GoogleAnalyticsProperty.id == property_id,
                    GoogleAnalyticsProperty.user_id == auth.user_id,
                    GoogleAnalyticsProperty.is_active == True
                )
            )
            property_obj = result.scalar_one_or_none()
            
            if not property_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="無效的 GA4 屬性或無權限使用"
                )
        
        # 檢查用戶的 API Key 數量限制
        from sqlalchemy import select, func
        
        result = await db.execute(
            select(func.count(UserApiKey.id)).where(
                UserApiKey.user_id == auth.user_id,
                UserApiKey.is_active == True
            )
        )
        current_count = result.scalar()
        
        if current_count >= 10:  # 限制每個用戶最多10個API Key
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已達到 API Key 數量上限（10個）"
            )
        
        # 生成唯一的 API Key
        def generate_api_key():
            # 生成格式：ga4_開頭 + 40個隨機字符
            alphabet = string.ascii_letters + string.digits
            random_part = ''.join(secrets.choice(alphabet) for _ in range(40))
            return f"ga4_{random_part}"
        
        # 確保 API Key 唯一
        api_key = generate_api_key()
        while True:
            result = await db.execute(
                select(UserApiKey).where(UserApiKey.api_key == api_key)
            )
            if not result.scalar_one_or_none():
                break
            api_key = generate_api_key()
        
        # 創建新的 API Key
        new_api_key = UserApiKey(
            user_id=auth.user_id,
            property_id=property_obj.id if property_obj else None,
            key_name=key_name,
            description=description,
            api_key=api_key,
            is_active=True
        )
        
        db.add(new_api_key)
        await db.commit()
        await db.refresh(new_api_key)
        
        property_info = None
        if property_obj:
            property_info = {
                "id": property_obj.id,
                "property_id": property_obj.property_id,
                "property_name": property_obj.property_name
            }
        
        logger.info(f"用戶 {auth.user_name} 創建了新的 API Key: {key_name}" + 
                   (f" (綁定屬性: {property_obj.property_name})" if property_obj else " (無綁定屬性)"))
        
        return {
            "message": "API Key 創建成功",
            "api_key": {
                "id": new_api_key.id,
                "name": new_api_key.key_name,
                "description": new_api_key.description,
                "api_key": new_api_key.api_key,
                "property": property_info,
                "created_at": new_api_key.created_at.isoformat(),
                "is_active": new_api_key.is_active
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"創建 API Key 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="創建 API Key 失敗"
        )

@app.get("/api/user/api-keys")
async def get_user_api_keys(
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """獲取用戶的 API Keys"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import UserApiKey
        from sqlalchemy import select, desc
        
        # 查詢用戶的所有有效 API Key，包含關聯的屬性
        result = await db.execute(
            select(UserApiKey, GoogleAnalyticsProperty).outerjoin(
                GoogleAnalyticsProperty, UserApiKey.property_id == GoogleAnalyticsProperty.id
            ).where(
                UserApiKey.user_id == auth.user_id,
                UserApiKey.is_active == True
            ).order_by(desc(UserApiKey.created_at))
        )
        
        api_key_results = result.all()
        
        # 轉換為返回格式
        api_keys_data = []
        for key, property_obj in api_key_results:
            property_info = None
            if property_obj:
                property_info = {
                    "id": property_obj.id,
                    "property_id": property_obj.property_id,
                    "property_name": property_obj.property_name
                }
            
            api_keys_data.append({
                "id": key.id,
                "name": key.key_name,
                "description": key.description,
                "api_key": key.api_key,
                "property": property_info,
                "created_at": key.created_at.isoformat(),
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "is_active": key.is_active
            })
        
        return {"api_keys": api_keys_data}
        
    except Exception as e:
        logger.error(f"獲取 API Key 列表失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="獲取 API Key 列表失敗"
        )

@app.delete("/api/user/api-keys/{key_id}")
async def delete_user_api_key(
    key_id: int,
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """刪除用戶的 API Key"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import UserApiKey
        from sqlalchemy import select
        
        # 查找 API Key
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.id == key_id,
                UserApiKey.user_id == auth.user_id,
                UserApiKey.is_active == True
            )
        )
        
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API Key 不存在或無權限刪除"
            )
        
        # 軟刪除（設為不活躍）
        api_key.is_active = False
        await db.commit()
        
        logger.info(f"用戶 {auth.user_name} 刪除了 API Key: {api_key.key_name}")
        
        return {"message": "API Key 已成功刪除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除 API Key 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刪除 API Key 失敗"
        )

@app.post("/api/user/properties")
async def add_user_property(
    request: dict,
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """添加 GA4 屬性"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import GoogleAnalyticsProperty
        from sqlalchemy import select
        
        # 驗證輸入
        property_id = request.get("property_id", "").strip()
        property_name = request.get("property_name", "").strip()
        
        if not property_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GA4 屬性 ID 不能為空"
            )
        
        if not property_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="屬性名稱不能為空"
            )
        
        # 檢查是否已存在
        result = await db.execute(
            select(GoogleAnalyticsProperty).where(
                GoogleAnalyticsProperty.user_id == auth.user_id,
                GoogleAnalyticsProperty.property_id == property_id,
                GoogleAnalyticsProperty.is_active == True
            )
        )
        existing_property = result.scalar_one_or_none()
        
        if existing_property:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此 GA4 屬性已經添加過了"
            )
        
        # 檢查用戶屬性數量限制
        from sqlalchemy import func
        result = await db.execute(
            select(func.count(GoogleAnalyticsProperty.id)).where(
                GoogleAnalyticsProperty.user_id == auth.user_id,
                GoogleAnalyticsProperty.is_active == True
            )
        )
        current_count = result.scalar()
        
        if current_count >= 20:  # 限制每個用戶最多20個屬性
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已達到 GA4 屬性數量上限（20個）"
            )
        
        # 創建新屬性
        new_property = GoogleAnalyticsProperty(
            user_id=auth.user_id,
            property_id=property_id,
            property_name=property_name,
            is_active=True
        )
        
        db.add(new_property)
        await db.commit()
        await db.refresh(new_property)
        
        logger.info(f"用戶 {auth.user_name} 添加了新的 GA4 屬性: {property_name} ({property_id})")
        
        return {
            "message": "GA4 屬性添加成功",
            "property": {
                "id": new_property.id,
                "property_id": new_property.property_id,
                "property_name": new_property.property_name,
                "created_at": new_property.created_at.isoformat(),
                "is_active": new_property.is_active
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加 GA4 屬性失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                         detail="添加 GA4 屬性失敗"
         )

@app.get("/api/user/properties")
async def get_user_properties(
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """獲取用戶的 GA4 屬性列表"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import GoogleAnalyticsProperty
        from sqlalchemy import select, desc
        
        # 查詢用戶的所有有效 GA4 屬性
        result = await db.execute(
            select(GoogleAnalyticsProperty).where(
                GoogleAnalyticsProperty.user_id == auth.user_id,
                GoogleAnalyticsProperty.is_active == True
            ).order_by(desc(GoogleAnalyticsProperty.created_at))
        )
        
        properties = result.scalars().all()
        
        # 轉換為返回格式
        properties_data = []
        for prop in properties:
            properties_data.append({
                "id": prop.id,
                "property_id": prop.property_id,
                "property_name": prop.property_name,
                "website_url": prop.website_url,
                "is_default": prop.is_default,
                "created_at": prop.created_at.isoformat(),
                "is_active": prop.is_active
            })
        
        return {"properties": properties_data}
        
    except Exception as e:
        logger.error(f"獲取 GA4 屬性列表失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="獲取 GA4 屬性列表失敗"
        )

@app.delete("/api/user/properties/{property_id}")
async def delete_user_property(
    property_id: int,
    auth: AuthenticationResult = Depends(verify_authentication),
    db: AsyncSession = Depends(get_db)
):
    """刪除用戶的 GA4 屬性"""
    if auth.user_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅支援 OAuth 用戶"
        )
    
    try:
        from models import GoogleAnalyticsProperty
        from sqlalchemy import select
        
        # 查找 GA4 屬性
        result = await db.execute(
            select(GoogleAnalyticsProperty).where(
                GoogleAnalyticsProperty.id == property_id,
                GoogleAnalyticsProperty.user_id == auth.user_id,
                GoogleAnalyticsProperty.is_active == True
            )
        )
        
        property_obj = result.scalar_one_or_none()
        
        if not property_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="GA4 屬性不存在或無權限刪除"
            )
        
        # 軟刪除（設為不活躍）
        property_obj.is_active = False
        await db.commit()
        
        logger.info(f"用戶 {auth.user_name} 刪除了 GA4 屬性: {property_obj.property_name} ({property_obj.property_id})")
        
        return {"message": "GA4 屬性已成功移除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除 GA4 屬性失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刪除 GA4 屬性失敗"
        )

@app.get("/oauth/status")
async def oauth_status():
    """OAuth 配置狀態診斷"""
    status_info = {
        "oauth_mode_enabled": ENABLE_OAUTH_MODE,
        "oauth_handler_enabled": oauth_handler.enabled,
        "google_client_id_configured": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "google_client_secret_configured": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "oauth_redirect_uri_configured": bool(os.getenv("OAUTH_REDIRECT_URI")),
        "overall_oauth_available": ENABLE_OAUTH_MODE and oauth_handler.enabled
    }
    
    # 檢查缺少的配置
    missing_configs = []
    if ENABLE_OAUTH_MODE and not oauth_handler.enabled:
        if not os.getenv("GOOGLE_CLIENT_ID"):
            missing_configs.append("GOOGLE_CLIENT_ID")
        if not os.getenv("GOOGLE_CLIENT_SECRET"):
            missing_configs.append("GOOGLE_CLIENT_SECRET")
    
    return {
        "status": status_info,
        "missing_configs": missing_configs,
        "message": "OAuth 診斷完成" if status_info["overall_oauth_available"] else "OAuth 配置不完整",
        "recommendation": "請檢查 .env 文件中的 OAuth 配置" if missing_configs else "OAuth 配置正常"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_v2:app", host="0.0.0.0", port=8000, reload=True) 