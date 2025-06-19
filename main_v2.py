import os
import logging
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# 載入環境變數
load_dotenv()

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 FastAPI 應用
app = FastAPI(
    title="GA4 Realtime API Service V2",
    description="BlockTempo GA4 多租戶即時分析服務 - 支援 OAuth 和 API Key 雙模式",
    version="2.0.0"
)

# 自定義 OpenAPI schema，隱藏內部端點
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title="GA4 Analytics API Service",
        version="2.0.0",
        description="""
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
        """,
        routes=app.routes,
    )
    
    # 過濾內部端點
    public_paths = [
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
        "/analytics/performance",
        "/auth/google/url",
        "/auth/status"
    ]
    
    filtered_paths = {}
    for path in public_paths:
        if path in openapi_schema["paths"]:
            filtered_paths[path] = openapi_schema["paths"][path]
    
    openapi_schema["paths"] = filtered_paths
    
    # 添加安全定義
    openapi_schema["components"] = {
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
    }
    
    openapi_schema["security"] = [
        {"ApiKeyAuth": []},
        {"BearerAuth": []}
    ]
    
    # 設置每個端點的安全要求
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

# 包含路由模組
from routers import analytics, auth
from routers import dashboard
# from routers.user import router as user_router  # 稍後創建

app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
# app.include_router(user_router)  # 稍後啟用

# 基礎端點
@app.get("/", response_model=dict)
async def root():
    """API 根端點"""
    return {
        "message": "GA4 Realtime API Service V2",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "features": {
            "oauth_authentication": True,
            "api_key_authentication": True,
            "realtime_analytics": True,
            "historical_analytics": True,
            "multi_tenant": True
        }
    }

@app.get("/health", response_model=dict)
async def health_check():
    """健康檢查端點"""
    try:
        from database import test_database_connection
        from oauth import oauth_handler
        
        # 測試資料庫連接
        db_status = "healthy"
        try:
            await test_database_connection()
        except Exception as e:
            logger.warning(f"資料庫連接測試失敗: {e}")
            db_status = "unavailable"
        
        # 檢查 OAuth 狀態
        oauth_status = "enabled" if oauth_handler.enabled else "disabled"
        
        # 檢查環境變數
        required_vars = ["GA4_PROPERTY_ID", "SERVICE_ACCOUNT_JSON"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        return {
            "status": "healthy",
            "version": "2.0.0",
            "database": db_status,
            "oauth": oauth_status,
            "environment": {
                "missing_variables": missing_vars,
                "configured": len(missing_vars) == 0
            },
            "services": {
                "ga4_analytics": "available",
                "authentication": "available",
                "rate_limiting": "active"
            }
        }
    
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """簡化的登入頁面"""
    login_html = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GA4 Analytics API - 登入</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            
            .login-container {
                background: white;
                border-radius: 20px;
                box-shadow: 0 25px 50px rgba(0,0,0,0.15);
                padding: 50px;
                max-width: 500px;
                width: 100%;
                text-align: center;
            }
            
            .logo {
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 20px;
                margin: 0 auto 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 36px;
                font-weight: bold;
            }
            
            h1 {
                color: #2c3e50;
                margin-bottom: 15px;
                font-size: 28px;
                font-weight: 600;
            }
            
            .subtitle {
                color: #7f8c8d;
                margin-bottom: 40px;
                font-size: 16px;
                line-height: 1.5;
            }
            
            .oauth-button {
                background: #4285f4;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                width: 100%;
                margin-bottom: 30px;
                transition: all 0.3s ease;
                text-decoration: none;
            }
            
            .oauth-button:hover {
                background: #3367d6;
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(66, 133, 244, 0.3);
            }
            
            .divider {
                margin: 30px 0;
                text-align: center;
                position: relative;
                color: #95a5a6;
            }
            
            .divider::before {
                content: '';
                position: absolute;
                top: 50%;
                left: 0;
                right: 0;
                height: 1px;
                background: #ecf0f1;
            }
            
            .divider span {
                background: white;
                padding: 0 20px;
            }
            
            .api-key-info {
                background: #f8f9fc;
                border-radius: 12px;
                padding: 25px;
                text-align: left;
                border-left: 4px solid #667eea;
            }
            
            .api-key-info h3 {
                color: #2c3e50;
                margin-bottom: 15px;
                font-size: 18px;
            }
            
            .api-key-info p {
                color: #5a6c7d;
                line-height: 1.6;
                margin-bottom: 15px;
                font-size: 14px;
            }
            
            .api-key-info code {
                background: #e8f0fe;
                color: #1a73e8;
                padding: 4px 8px;
                border-radius: 4px;
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 13px;
            }
            
            .footer {
                margin-top: 40px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
            }
            
            .footer a {
                color: #667eea;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">GA</div>
            <h1>GA4 Analytics API</h1>
            <p class="subtitle">連接您的 Google Analytics 帳戶<br>開始使用強大的數據分析 API</p>
            
            <a href="/auth/google" class="oauth-button">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                使用 Google 帳戶登入
            </a>
            
            <div class="divider">
                <span>或</span>
            </div>
            
            <div class="api-key-info">
                <h3>使用 API Key</h3>
                <p>如果您已經有 API Key，可以直接在請求頭中使用：</p>
                <p><code>X-API-Key: your_api_key_here</code></p>
                <p>請聯繫管理員獲取您的專屬 API Key。</p>
            </div>
            
            <div class="footer">
                <p><a href="/docs">API 文檔</a> | <a href="/health">系統狀態</a></p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=login_html)

# Dashboard 路由已移至 routers/dashboard.py

# 錯誤處理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """統一的 HTTP 異常處理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path) if request else None
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """統一的一般異常處理"""
    logger.error(f"未處理的異常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "內部伺服器錯誤",
            "status_code": 500,
            "path": str(request.url.path) if request else None
        }
    )

# 啟動事件
@app.on_event("startup")
async def startup_event():
    """應用啟動時執行的初始化"""
    logger.info("GA4 Analytics API V2 正在啟動...")
    
    try:
        # 初始化資料庫
        from database import init_database
        await init_database()
        logger.info("資料庫初始化完成")
    except Exception as e:
        logger.warning(f"資料庫初始化失敗: {e}")
    
    logger.info("GA4 Analytics API V2 啟動完成")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_v2:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    ) 