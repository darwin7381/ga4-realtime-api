import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, OAuthToken, GoogleAnalyticsProperty
from oauth import oauth_handler, OAuthUserManager
from services.auth_service import AuthenticationResult, auth_service

logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
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
    ga4_properties: list

class UserInfoResponse(BaseModel):
    user_id: int
    email: str
    name: Optional[str]
    ga4_properties: list
    created_at: str

@router.get("/google")
async def google_oauth_init():
    """舊版本兼容：重定向到 OAuth URL"""
    if not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 服務未啟用"
        )
    
    auth_url, state = oauth_handler.get_authorization_url()
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

@router.get("/google/url", response_model=AuthUrlResponse)
async def get_google_oauth_url():
    """獲取 Google OAuth 授權 URL"""
    if not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 服務未啟用"
        )
    
    try:
        auth_url, state = oauth_handler.get_authorization_url()
        return AuthUrlResponse(
            auth_url=auth_url,
            state=state,
            message="請在新視窗中完成 Google 授權"
        )
    except Exception as e:
        logger.error(f"生成 OAuth URL 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"無法生成授權 URL: {str(e)}"
        )

@router.get("/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """OAuth 回調處理（HTML 版本）"""
    if not oauth_handler.enabled:
        return HTMLResponse(
            content="<h1>錯誤</h1><p>OAuth 服務未啟用</p>",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        # 處理 OAuth 回調
        result = await OAuthUserManager.handle_oauth_callback(
            db, code, state, oauth_handler
        )
        
        if result["success"]:
            user_data = result["user"]
            properties_data = result["ga4_properties"]
            
            # 生成成功頁面
            success_html = f"""
            <!DOCTYPE html>
            <html lang="zh-TW">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>授權成功 - GA4 Analytics API</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 40px 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        box-sizing: border-box;
                    }}
                    .container {{
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                        padding: 40px;
                        text-align: center;
                    }}
                    .success-icon {{
                        width: 80px;
                        height: 80px;
                        background: #4CAF50;
                        border-radius: 50%;
                        margin: 0 auto 30px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-size: 40px;
                    }}
                    h1 {{
                        color: #2c3e50;
                        margin-bottom: 20px;
                        font-size: 28px;
                    }}
                    .user-info {{
                        background: #f8f9fa;
                        border-radius: 10px;
                        padding: 25px;
                        margin: 30px 0;
                        text-align: left;
                    }}
                    .info-item {{
                        margin: 15px 0;
                        padding: 10px 0;
                        border-bottom: 1px solid #e9ecef;
                    }}
                    .info-item:last-child {{
                        border-bottom: none;
                    }}
                    .label {{
                        font-weight: bold;
                        color: #495057;
                        display: inline-block;
                        width: 120px;
                    }}
                    .value {{
                        color: #6c757d;
                    }}
                    .properties-list {{
                        margin-top: 15px;
                    }}
                    .property-item {{
                        background: white;
                        border: 1px solid #dee2e6;
                        border-radius: 5px;
                        padding: 10px;
                        margin: 5px 0;
                        font-size: 14px;
                    }}
                    .btn {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px 30px;
                        border: none;
                        border-radius: 25px;
                        font-size: 16px;
                        cursor: pointer;
                        text-decoration: none;
                        display: inline-block;
                        margin-top: 20px;
                        transition: transform 0.2s;
                    }}
                    .btn:hover {{
                        transform: translateY(-2px);
                    }}
                    .note {{
                        background: #e3f2fd;
                        border-left: 4px solid #2196F3;
                        padding: 15px;
                        margin-top: 30px;
                        border-radius: 5px;
                        text-align: left;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✓</div>
                    <h1>Google 授權成功！</h1>
                    <p>您已成功連接 Google Analytics 帳戶，現在可以使用 API 服務了。</p>
                    
                    <div class="user-info">
                        <h3 style="margin-top: 0; color: #2c3e50;">用戶資訊</h3>
                        <div class="info-item">
                            <span class="label">用戶ID:</span>
                            <span class="value">{user_data['id']}</span>
                        </div>
                        <div class="info-item">
                            <span class="label">電子郵件:</span>
                            <span class="value">{user_data['email']}</span>
                        </div>
                        <div class="info-item">
                            <span class="label">姓名:</span>
                            <span class="value">{user_data.get('name', '未提供')}</span>
                        </div>
                        <div class="info-item">
                            <span class="label">GA4 屬性:</span>
                            <div class="properties-list">
                                {chr(10).join([f'<div class="property-item">ID: {prop["property_id"]} - {prop["display_name"]}</div>' for prop in properties_data])}
                            </div>
                        </div>
                    </div>
                    
                    <a href="/dashboard" class="btn">進入控制面板</a>
                    
                    <div class="note">
                        <strong>📝 重要提醒：</strong><br>
                        • 您現在可以使用 OAuth token 來訪問 API<br>
                        • 請妥善保管您的 access token<br>
                        • 如需 API Key，請在控制面板中生成<br>
                        • 這個視窗可以安全關閉
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=success_html)
        else:
            error_html = f"""
            <!DOCTYPE html>
            <html lang="zh-TW">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>授權失敗 - GA4 Analytics API</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 40px 20px;
                        background: linear-gradient(135deg, #ff7e5f 0%, #feb47b 100%);
                        min-height: 100vh;
                        box-sizing: border-box;
                    }}
                    .container {{
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                        padding: 40px;
                        text-align: center;
                    }}
                    .error-icon {{
                        width: 80px;
                        height: 80px;
                        background: #f44336;
                        border-radius: 50%;
                        margin: 0 auto 30px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-size: 40px;
                    }}
                    h1 {{
                        color: #2c3e50;
                        margin-bottom: 20px;
                    }}
                    .error-details {{
                        background: #ffebee;
                        border: 1px solid #ffcdd2;
                        border-radius: 10px;
                        padding: 20px;
                        margin: 20px 0;
                        text-align: left;
                    }}
                    .btn {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px 30px;
                        border: none;
                        border-radius: 25px;
                        font-size: 16px;
                        cursor: pointer;
                        text-decoration: none;
                        display: inline-block;
                        margin-top: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">✗</div>
                    <h1>授權失敗</h1>
                    <p>抱歉，Google 授權過程中發生錯誤。</p>
                    
                    <div class="error-details">
                        <strong>錯誤詳情：</strong><br>
                        {result.get('error', '未知錯誤')}
                    </div>
                    
                    <a href="/auth/google" class="btn">重新授權</a>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=400)
    
    except Exception as e:
        logger.error(f"OAuth 回調處理失敗: {e}")
        error_html = f"""
        <!DOCTYPE html>
        <html lang="zh-TW">
        <head>
            <meta charset="UTF-8">
            <title>系統錯誤 - GA4 Analytics API</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background: white;
                    border-radius: 10px;
                    padding: 30px;
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .error {{
                    color: #d32f2f;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>系統錯誤</h1>
                <div class="error">授權處理過程中發生系統錯誤，請稍後重試。</div>
                <p>錯誤詳情：{str(e)}</p>
                <a href="/auth/google">重新授權</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

@router.get("/callback/json", response_model=OAuthCallbackResponse)
async def google_oauth_callback_json(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """OAuth 回調處理（JSON 版本）"""
    if not oauth_handler.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth 服務未啟用"
        )
    
    try:
        result = await OAuthUserManager.handle_oauth_callback(
            db, code, state, oauth_handler
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "OAuth 授權失敗")
            )
        
        user_data = result["user"]
        properties_data = result["ga4_properties"]
        
        return OAuthCallbackResponse(
            message="OAuth 授權成功",
            user_id=user_data["id"],
            email=user_data["email"],
            ga4_properties=properties_data
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth 回調處理失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth 處理失敗: {str(e)}"
        )

@router.get("/status")
async def oauth_status():
    """OAuth 服務狀態"""
    return {
        "oauth_enabled": oauth_handler.enabled,
        "oauth_configured": oauth_handler.enabled,
        "client_id_configured": bool(oauth_handler.client_id) if oauth_handler.enabled else False,
        "scopes": oauth_handler.scopes if oauth_handler.enabled else [],
        "message": "OAuth 服務正常運行" if oauth_handler.enabled else "OAuth 服務未啟用"
    } 