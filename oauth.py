import os
import json
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging

import httpx
from authlib.integrations.starlette_client import OAuth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.analytics.admin import AnalyticsAdminServiceClient
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from dotenv import load_dotenv

from models import User, OAuthToken, GoogleAnalyticsProperty

# 確保載入 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

# OAuth 配置
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Google OAuth 範圍
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

class GoogleOAuthHandler:
    """Google OAuth 處理器"""
    
    def __init__(self):
        # 設置屬性
        self.client_id = GOOGLE_CLIENT_ID
        self.client_secret = GOOGLE_CLIENT_SECRET
        self.redirect_uri = OAUTH_REDIRECT_URI
        self.scopes = GOOGLE_SCOPES
        
        # 詳細的配置檢查和調試信息
        client_id_ok = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_ID.strip())
        client_secret_ok = bool(GOOGLE_CLIENT_SECRET and GOOGLE_CLIENT_SECRET.strip())
        redirect_uri_ok = bool(OAUTH_REDIRECT_URI and OAUTH_REDIRECT_URI.strip())
        
        logger.info(f"OAuth 配置檢查:")
        logger.info(f"  GOOGLE_CLIENT_ID: {'✅' if client_id_ok else '❌'} ({'設定' if client_id_ok else '未設定'})")
        logger.info(f"  GOOGLE_CLIENT_SECRET: {'✅' if client_secret_ok else '❌'} ({'設定' if client_secret_ok else '未設定'})")
        logger.info(f"  OAUTH_REDIRECT_URI: {'✅' if redirect_uri_ok else '❌'} ({'設定' if redirect_uri_ok else '未設定'})")
        
        if not all([client_id_ok, client_secret_ok]):
            logger.warning("Google OAuth 配置不完整 - 缺少必要的 CLIENT_ID 或 CLIENT_SECRET")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Google OAuth 處理器初始化成功 ✅")
    
    def build_auth_url(self, state: str = None) -> str:
        """建立 OAuth 授權 URL"""
        if not self.enabled:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth 服務未配置"
            )
        
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": " ".join(GOOGLE_SCOPES),
            "response_type": "code",
            "access_type": "offline",  # 獲取 refresh token
            "prompt": "consent",  # 強制顯示同意畫面
            "state": state
        }
        
        from urllib.parse import urlencode
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        
        return auth_url, state
    
    def get_authorization_url(self, state: str = None):
        """獲取授權 URL (別名方法)"""
        return self.build_auth_url(state)
    
    async def exchange_code_for_tokens(self, code: str) -> Dict:
        """用授權碼換取 tokens"""
        if not self.enabled:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth 服務未配置"
            )
        
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_REDIRECT_URI
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                tokens = response.json()
                
                logger.info("成功獲取 OAuth tokens")
                return tokens
        
        except httpx.HTTPError as e:
            logger.error(f"OAuth token 交換失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="授權碼無效或已過期"
            )
    
    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """刷新 access token"""
        if not self.enabled:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth 服務未配置"
            )
        
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                tokens = response.json()
                
                logger.info("成功刷新 access token")
                return tokens
        
        except httpx.HTTPError as e:
            logger.error(f"Token 刷新失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 刷新失敗，請重新授權"
            )
    
    async def get_user_info(self, access_token: str) -> Dict:
        """獲取用戶基本資訊"""
        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(user_info_url, headers=headers)
                response.raise_for_status()
                user_info = response.json()
                
                logger.info(f"獲取用戶資訊成功: {user_info.get('email')}")
                return user_info
        
        except httpx.HTTPError as e:
            logger.error(f"獲取用戶資訊失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無法獲取用戶資訊"
            )
    
    def get_ga4_properties(self, access_token: str) -> List[Dict]:
        """獲取用戶的 GA4 屬性列表"""
        try:
            credentials = Credentials(token=access_token)
            client = AnalyticsAdminServiceClient(credentials=credentials)
            
            properties = []
            
            # 獲取所有帳戶
            for account in client.list_accounts():
                account_name = account.name
                logger.info(f"處理帳戶: {account_name}")
                
                # 獲取帳戶下的所有屬性
                try:
                    for property_obj in client.list_properties(parent=account_name):
                        property_id = property_obj.name.split("/")[-1]
                        
                        # 只處理 GA4 屬性 (property_type == PROPERTY_TYPE_GA4)
                        if hasattr(property_obj, 'property_type') and property_obj.property_type.name == "PROPERTY_TYPE_GA4":
                            properties.append({
                                "property_id": property_id,
                                "display_name": property_obj.display_name,
                                "property_type": "GA4",
                                "parent": account_name,
                                "create_time": property_obj.create_time.isoformat() if property_obj.create_time else None
                            })
                            logger.info(f"找到 GA4 屬性: {property_obj.display_name} (ID: {property_id})")
                        
                except Exception as account_error:
                    logger.warning(f"無法獲取帳戶 {account_name} 的屬性: {account_error}")
                    continue
            
            logger.info(f"總共獲取到 {len(properties)} 個 GA4 屬性")
            return properties
        
        except Exception as e:
            logger.error(f"獲取 GA4 屬性失敗: {e}")
            logger.error(f"錯誤類型: {type(e)}")
            return []

class OAuthUserManager:
    """OAuth 用戶管理器"""
    
    @staticmethod
    async def handle_oauth_callback(
        db: AsyncSession, 
        code: str, 
        state: str, 
        oauth_handler: GoogleOAuthHandler
    ) -> dict:
        """
        處理 OAuth 回調的完整流程
        
        Args:
            db: 資料庫會話
            code: 授權碼
            state: 狀態參數
            oauth_handler: OAuth 處理器
        
        Returns:
            dict: 包含處理結果的字典
        """
        try:
            # 1. 用授權碼換取 tokens
            logger.info("開始處理 OAuth 回調...")
            tokens = await oauth_handler.exchange_code_for_tokens(code)
            logger.info("成功獲取 OAuth tokens")
            
            # 2. 獲取用戶資訊
            access_token = tokens.get("access_token")
            user_info = await oauth_handler.get_user_info(access_token)
            logger.info(f"獲取用戶資訊: {user_info.get('email')}")
            
            # 3. 獲取 GA4 屬性
            ga4_properties = oauth_handler.get_ga4_properties(access_token)
            logger.info(f"獲取到 {len(ga4_properties)} 個 GA4 屬性")
            
            # 4. 創建或更新用戶
            user = await OAuthUserManager.create_or_update_user(
                db, user_info, tokens, ga4_properties
            )
            logger.info(f"用戶處理完成: {user.email}")
            
            # 5. 準備返回數據
            user_data = {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            }
            
            return {
                "success": True,
                "message": "OAuth 授權成功",
                "user": user_data,
                "ga4_properties": ga4_properties,
                "tokens_info": {
                    "has_access_token": bool(tokens.get("access_token")),
                    "has_refresh_token": bool(tokens.get("refresh_token")),
                    "expires_in": tokens.get("expires_in"),
                    "scope": tokens.get("scope")
                }
            }
            
        except Exception as e:
            logger.error(f"OAuth 回調處理失敗: {e}")
            logger.error(f"錯誤類型: {type(e)}")
            
            return {
                "success": False,
                "error": str(e),
                "message": "OAuth 授權失敗"
            }
    
    @staticmethod
    async def create_or_update_user(
        db: AsyncSession, 
        user_info: Dict, 
        tokens: Dict,
        ga4_properties: List[Dict] = None
    ) -> User:
        """創建或更新用戶"""
        email = user_info.get("email")
        name = user_info.get("name")
        
        # 查找現有用戶
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if user:
            # 更新現有用戶
            user.name = name
            user.updated_at = datetime.utcnow()
            user.is_active = True
            logger.info(f"更新現有用戶: {email}")
        else:
            # 創建新用戶
            user = User(
                email=email,
                name=name,
                is_active=True
            )
            db.add(user)
            await db.flush()  # 獲取用戶 ID
            logger.info(f"創建新用戶: {email}")
        
        # 儲存或更新 OAuth tokens
        await OAuthUserManager.save_oauth_token(db, user.id, tokens)
        
        # 儲存 GA4 屬性
        if ga4_properties:
            await OAuthUserManager.save_ga4_properties(db, user.id, ga4_properties)
        
        await db.commit()
        return user
    
    @staticmethod
    async def save_oauth_token(db: AsyncSession, user_id: int, tokens: Dict):
        """儲存 OAuth token"""
        # 撤銷現有的 token
        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id,
                OAuthToken.is_revoked == False
            )
        )
        existing_tokens = result.scalars().all()
        for token in existing_tokens:
            token.is_revoked = True
        
        # 創建新的 token 記錄
        expires_in = tokens.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        oauth_token = OAuthToken(
            user_id=user_id,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            scope=tokens.get("scope"),
            token_type=tokens.get("token_type", "Bearer")
        )
        
        db.add(oauth_token)
        logger.info(f"儲存新的 OAuth token，用戶 ID: {user_id}")
    
    @staticmethod
    async def save_ga4_properties(db: AsyncSession, user_id: int, properties: List[Dict]):
        """儲存 GA4 屬性"""
        # 先標記現有屬性為非活躍
        result = await db.execute(
            select(GoogleAnalyticsProperty).where(
                GoogleAnalyticsProperty.user_id == user_id
            )
        )
        existing_properties = result.scalars().all()
        for prop in existing_properties:
            prop.is_active = False
        
        # 添加或更新屬性
        for prop_info in properties:
            property_id = prop_info.get("property_id")
            
            # 查找現有屬性
            result = await db.execute(
                select(GoogleAnalyticsProperty).where(
                    GoogleAnalyticsProperty.user_id == user_id,
                    GoogleAnalyticsProperty.property_id == property_id
                )
            )
            existing_prop = result.scalar_one_or_none()
            
            if existing_prop:
                # 更新現有屬性
                existing_prop.property_name = prop_info.get("display_name")
                existing_prop.is_active = True
                existing_prop.updated_at = datetime.utcnow()
            else:
                # 創建新屬性
                ga4_property = GoogleAnalyticsProperty(
                    user_id=user_id,
                    property_id=property_id,
                    property_name=prop_info.get("display_name"),
                    is_active=True
                )
                db.add(ga4_property)
        
        logger.info(f"更新用戶 {user_id} 的 GA4 屬性，共 {len(properties)} 個")
    
    @staticmethod
    async def get_user_active_token(db: AsyncSession, user_id: int) -> Optional[OAuthToken]:
        """獲取用戶的有效 token"""
        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id,
                OAuthToken.is_revoked == False,
                OAuthToken.expires_at > datetime.utcnow()
            ).order_by(OAuthToken.created_at.desc())
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def refresh_user_token(db: AsyncSession, user_id: int, oauth_handler: GoogleOAuthHandler) -> Optional[str]:
        """刷新用戶的 access token"""
        # 獲取最新的 refresh token
        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id,
                OAuthToken.refresh_token.isnot(None),
                OAuthToken.is_revoked == False
            ).order_by(OAuthToken.created_at.desc())
        )
        token_record = result.scalar_one_or_none()
        
        if not token_record or not token_record.refresh_token:
            logger.warning(f"用戶 {user_id} 沒有有效的 refresh token")
            return None
        
        try:
            # 刷新 token
            new_tokens = await oauth_handler.refresh_access_token(token_record.refresh_token)
            
            # 儲存新的 token
            await OAuthUserManager.save_oauth_token(db, user_id, new_tokens)
            await db.commit()
            
            return new_tokens.get("access_token")
        
        except Exception as e:
            logger.error(f"刷新用戶 {user_id} 的 token 失敗: {e}")
            return None

# 全域 OAuth 處理器實例
oauth_handler = GoogleOAuthHandler() 