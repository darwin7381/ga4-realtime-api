import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from pydantic import BaseModel
from google.analytics.data_v1beta.types import RunRealtimeReportRequest
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.auth_service import AuthenticationResult, auth_service
from services.ga4_service import ga4_service
from ga4_extensions import GA4DataService

logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(
    prefix="",
    tags=["Analytics"],
    responses={404: {"description": "Not found"}},
)

# 響應模型
class ActiveUsersResponse(BaseModel):
    user: str
    user_type: str
    activeUsers: int
    property_id: str
    timestamp: str
    status: str = "success"

class ActiveUsersResponseV1(BaseModel):
    user: str
    activeUsers: int
    timestamp: str
    status: str = "success"

# 依賴函數
async def verify_auth(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> AuthenticationResult:
    """認證依賴函數"""
    return await auth_service.verify_authentication(request, x_api_key, authorization, db)

# 初始化GA4數據服務
try:
    ga4_data_service = GA4DataService()
    logger.info("GA4DataService 初始化成功")
except Exception as e:
    logger.warning(f"GA4DataService 初始化失敗: {str(e)}")
    ga4_data_service = None

@router.get("/active-users")
async def get_active_users(
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取即時在線人數"""
    try:
        # 獲取GA4客戶端
        client = ga4_service.get_ga4_client(auth)
        
        if not auth.ga4_property_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未找到有效的GA4屬性ID"
            )
        
        # 構建請求
        request_data = RunRealtimeReportRequest(
            property=f"properties/{auth.ga4_property_id}",
            metrics=[{"name": "activeUsers"}]
        )
        
        # 執行查詢
        response = client.run_realtime_report(request_data)
        
        # 解析結果
        active_users = 0
        if response.rows:
            active_users = int(response.rows[0].metric_values[0].value)
        
        # V1 兼容格式（舊版本）
        if auth.user_type == "api_key":
            return ActiveUsersResponseV1(
                user=auth.user_name,
                activeUsers=active_users,
                timestamp=datetime.now().isoformat(),
                status="success"
            )
        
        # V2 完整格式
        return ActiveUsersResponse(
            user=auth.user_name,
            user_type=auth.user_type,
            activeUsers=active_users,
            property_id=auth.ga4_property_id,
            timestamp=datetime.now().isoformat(),
            status="success"
        )
        
    except Exception as e:
        logger.error(f"獲取在線人數失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/realtime/overview")
async def get_realtime_overview(
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取即時數據總覽"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        overview = ga4_data_service.get_realtime_overview()
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "timestamp": datetime.now().isoformat(),
            "data": overview,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取即時總覽失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/realtime/top-pages")
async def get_realtime_top_pages(
    limit: int = 10,
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取即時熱門頁面"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        top_pages = ga4_data_service.get_realtime_top_pages(limit)
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "timestamp": datetime.now().isoformat(),
            "data": top_pages,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取即時熱門頁面失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/traffic-sources")
async def get_traffic_sources(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取流量來源分析"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        traffic_sources = ga4_data_service.get_traffic_sources(
            start_date, end_date
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": traffic_sources,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取流量來源失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/pageviews")
async def get_pageviews_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取頁面瀏覽量分析"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        pageviews = ga4_data_service.get_pageviews_analytics(
            start_date, end_date
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": pageviews,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取頁面瀏覽量失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/devices")
async def get_device_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取設備分析數據"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        devices = ga4_data_service.get_device_analytics(
            start_date, end_date
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": devices,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取設備分析失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/geographic")
async def get_geographic_data(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取地理位置數據"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        geographic = ga4_data_service.get_geographic_data(
            start_date, end_date
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": geographic,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取地理位置數據失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/top-pages")
async def get_top_pages_analytics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取熱門頁面分析（包含完整URL）"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        top_pages = ga4_data_service.get_top_pages_analytics(
            start_date, end_date, limit
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": top_pages,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取熱門頁面分析失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/search-terms")
async def get_search_terms(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取搜索詞分析"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        search_terms = ga4_data_service.get_search_terms(
            start_date, end_date, limit
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": search_terms,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取搜索詞分析失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        )

@router.get("/analytics/performance")
async def get_performance_metrics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 20,
    auth: AuthenticationResult = Depends(verify_auth)
):
    """獲取性能指標分析"""
    try:
        if not ga4_data_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GA4數據服務未初始化"
            )
        
        # 暫時使用預設的 GA4DataService 實例
        performance = ga4_data_service.get_performance_metrics(
            start_date, end_date, limit
        )
        
        return {
            "user": auth.user_name,
            "user_type": auth.user_type,
            "property_id": auth.ga4_property_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "data": performance,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"獲取性能指標失敗: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢失敗: {str(e)}"
        ) 