import os
import time
import logging
from typing import Optional
from datetime import datetime

from fastapi import HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User, OAuthToken, UserApiKey, GoogleAnalyticsProperty, ApiUsageLog
from oauth import oauth_handler, OAuthUserManager

logger = logging.getLogger(__name__)

class AuthenticationResult:
    def __init__(self, user_name: str, user_type: str, user_id: Optional[int] = None, 
                 ga4_property_id: Optional[str] = None, access_token: Optional[str] = None):
        self.user_name = user_name
        self.user_type = user_type  # "oauth", "user_api_key", or "api_key"
        self.user_id = user_id
        self.ga4_property_id = ga4_property_id
        self.access_token = access_token

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

# 全局速率限制實例
rate_limiter = RateLimiter()

class AuthService:
    def __init__(self):
        self.GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")
        self.ENABLE_OAUTH_MODE = os.getenv("ENABLE_OAUTH_MODE", "true").lower() == "true"
        self.ENABLE_API_KEY_MODE = os.getenv("ENABLE_API_KEY_MODE", "true").lower() == "true"
        self.API_KEYS = self._load_api_keys() if self.ENABLE_API_KEY_MODE else {}
    
    def _load_api_keys(self):
        """載入靜態 API Key 配置，格式：API_KEY_[USER]=key"""
        api_keys = {}
        for key, value in os.environ.items():
            if key.startswith("API_KEY_"):
                user_name = key.replace("API_KEY_", "").lower()
                api_keys[value] = user_name
        
        if not api_keys:
            logger.warning("未找到任何靜態 API Key 配置")
        else:
            logger.info(f"已載入 {len(api_keys)} 個靜態 API Key")
        
        return api_keys
    
    async def log_api_usage(self, auth_result: AuthenticationResult, request: Request, 
                           endpoint: str, status_code: int, db: AsyncSession = None,
                           response_time_ms: int = None, error_message: str = None):
        """記錄 API 使用"""
        if db is None:
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
    
    async def verify_authentication(
        self,
        request: Request,
        x_api_key: Optional[str] = None,
        authorization: Optional[str] = None,
        db: AsyncSession = None
    ) -> AuthenticationResult:
        """統一認證處理：支援 OAuth Bearer Token 和 API Key"""
        
        # 嘗試 OAuth 認證
        if (authorization and authorization.startswith("Bearer ") and 
            self.ENABLE_OAUTH_MODE and oauth_handler.enabled and db is not None):
            
            return await self._verify_oauth_token(authorization, request, db)
        
        # 嘗試 API Key 認證
        elif x_api_key and self.ENABLE_API_KEY_MODE:
            return await self._verify_api_key(x_api_key, request, db)
        
        # 沒有提供任何認證資訊
        else:
            missing_auth = []
            if self.ENABLE_OAUTH_MODE and oauth_handler.enabled:
                missing_auth.append("Authorization Bearer token")
            if self.ENABLE_API_KEY_MODE:
                missing_auth.append("X-API-Key header")
            
            if not missing_auth:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="服務未配置認證方式"
                )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"需要認證：{' 或 '.join(missing_auth)}"
            )
    
    async def _verify_oauth_token(self, authorization: str, request: Request, 
                                db: AsyncSession) -> AuthenticationResult:
        """驗證 OAuth token"""
        try:
            token = authorization.replace("Bearer ", "")
            
            # 查找用戶和 token
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
            property_id = await self._get_user_default_property(db, user.id)
            
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
    
    async def _verify_api_key(self, x_api_key: str, request: Request, 
                            db: AsyncSession = None) -> AuthenticationResult:
        """驗證 API Key"""
        
        # 首先檢查數據庫中的用戶 API Key
        if db is not None:
            try:
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
                    user_api_key.last_used_at = datetime.utcnow()
                    await db.commit()
                    
                    # 如果 API Key 沒有關聯特定屬性，使用默認的 GA4_PROPERTY_ID
                    property_id = property_obj.property_id if property_obj else self.GA4_PROPERTY_ID
                    
                    logger.info(f"用戶 API Key 認證成功 - 用戶: {user.email}, GA4屬性: {property_id}")
                    
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
        if x_api_key in self.API_KEYS:
            user_name = self.API_KEYS[x_api_key]
            
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
                ga4_property_id=self.GA4_PROPERTY_ID
            )
        
        # 如果兩種 API Key 都不匹配
        logger.warning(f"無效的API Key嘗試: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的API Key"
        )
    
    async def _get_user_default_property(self, db: AsyncSession, user_id: int) -> Optional[str]:
        """獲取用戶的預設 GA4 屬性"""
        try:
            result = await db.execute(
                select(GoogleAnalyticsProperty).where(
                    GoogleAnalyticsProperty.user_id == user_id,
                    GoogleAnalyticsProperty.is_active == True,
                    GoogleAnalyticsProperty.is_default == True
                )
            )
            default_property = result.scalar_one_or_none()
            
            if not default_property:
                # 如果沒有預設屬性，使用第一個活躍屬性
                result = await db.execute(
                    select(GoogleAnalyticsProperty).where(
                        GoogleAnalyticsProperty.user_id == user_id,
                        GoogleAnalyticsProperty.is_active == True
                    ).limit(1)
                )
                default_property = result.scalar_one_or_none()
            
            return default_property.property_id if default_property else None
        
        except Exception as e:
            logger.error(f"獲取用戶預設屬性失敗: {e}")
            return None

# 全局認證服務實例
auth_service = AuthService() 