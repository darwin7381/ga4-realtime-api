import os
import json
import logging
from typing import Optional

from fastapi import HTTPException, status
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

from services.auth_service import AuthenticationResult

logger = logging.getLogger(__name__)

class GA4Service:
    def __init__(self):
        self.SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
    
    def get_ga4_client(self, auth_result: AuthenticationResult):
        """根據認證結果獲取對應的 GA4 客戶端"""
        try:
            if auth_result.user_type == "oauth":
                # OAuth 模式：使用用戶的 access token
                credentials = Credentials(token=auth_result.access_token)
                client = BetaAnalyticsDataClient(credentials=credentials)
            else:
                # API Key 模式：使用 Service Account
                if not self.SERVICE_ACCOUNT_JSON:
                    raise ValueError("SERVICE_ACCOUNT_JSON 環境變數未設定")
                
                # 預處理 SERVICE_ACCOUNT_JSON - 修正控制字符問題
                processed_json = self.SERVICE_ACCOUNT_JSON.replace('\\n', '\\\\n').replace('\n', '\\n')
                
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
                detail=f"GA4服務初始化失敗: {str(e)}"
            )

# 全局 GA4 服務實例
ga4_service = GA4Service() 