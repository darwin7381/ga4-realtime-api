import logging
import secrets
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import User, UserApiKey, GoogleAnalyticsProperty
from services.auth_service import AuthenticationResult, auth_service

logger = logging.getLogger(__name__)

# 創建路由器
router = APIRouter(
    prefix="",
    tags=["Dashboard"],
    responses={404: {"description": "Not found"}},
)

# 響應模型
class ApiKeyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    key: str
    property_id: Optional[str]
    created_at: str
    is_active: bool

class CreateApiKeyRequest(BaseModel):
    name: str
    description: Optional[str] = None
    property_id: Optional[str] = None

@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard():
    """簡潔的用戶控制面板"""
    dashboard_html = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>控制面板 - GA4 Analytics API</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1000px;
                margin: 0 auto;
            }
            
            .card {
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                padding: 30px;
                margin-bottom: 20px;
            }
            
            .header {
                text-align: center;
                margin-bottom: 20px;
            }
            
            .user-info {
                display: flex;
                align-items: center;
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .avatar {
                width: 50px;
                height: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
            }
            
            .btn {
                background: #4285f4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                display: inline-block;
                margin: 5px;
            }
            
            .btn:hover { background: #3367d6; transform: translateY(-1px); }
            .btn-success { background: #34a853; }
            .btn-success:hover { background: #2e7d32; }
            .btn-danger { background: #ea4335; }
            .btn-danger:hover { background: #c5221f; }
            
            .form-group {
                margin-bottom: 15px;
            }
            
            .form-label {
                display: block;
                font-weight: 600;
                margin-bottom: 5px;
                color: #333;
            }
            
            .form-input {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                box-sizing: border-box;
            }
            
            .api-key-item {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 10px;
                display: flex;
                justify-content: space-between;
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
                padding: 5px 8px;
                border-radius: 4px;
                font-size: 12px;
                color: #495057;
                word-break: break-all;
                margin: 5px 0;
            }
            
            .loading { text-align: center; color: #666; padding: 20px; }
            .error { color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 6px; margin: 10px 0; }
            .success { color: #155724; background: #d4edda; padding: 10px; border-radius: 6px; margin: 10px 0; }
            
            .tabs {
                display: flex;
                border-bottom: 2px solid #e9ecef;
                margin-bottom: 20px;
            }
            
            .tab-btn {
                background: none;
                border: none;
                padding: 12px 20px;
                font-size: 14px;
                cursor: pointer;
                color: #666;
                border-bottom: 3px solid transparent;
                transition: all 0.2s;
            }
            
            .tab-btn.active {
                color: #4285f4;
                border-bottom-color: #4285f4;
            }
            
            .tab-content { display: none; }
            .tab-content.active { display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <div class="user-info">
                    <div class="avatar" id="user-avatar">JL</div>
                    <div>
                        <h2 id="user-name">Joey Luo</h2>
                        <p id="user-email">joey@cryptoxlab.com</p>
                    </div>
                </div>
                <h1>GA4 Analytics API 控制面板</h1>
                <p>管理您的 API 金鑰和 Google Analytics 屬性</p>
            </div>
            
            <div class="card">
                <div class="tabs">
                    <button class="tab-btn active" onclick="showTab('api-keys')">🔑 API Keys</button>
                    <button class="tab-btn" onclick="showTab('properties')">📊 GA4 屬性</button>
                    <button class="tab-btn" onclick="showTab('docs')">📖 文檔</button>
                </div>
                
                <!-- API Keys 管理 -->
                <div id="api-keys-tab" class="tab-content active">
                    <h3>API Keys 管理</h3>
                    
                    <!-- 創建新 API Key -->
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h4>創建新 API Key</h4>
                        <div class="form-group">
                            <label class="form-label">名稱</label>
                            <input type="text" class="form-input" id="api-key-name" placeholder="例如：我的專案 API Key">
                        </div>
                        <div class="form-group">
                            <label class="form-label">描述 (可選)</label>
                            <input type="text" class="form-input" id="api-key-description" placeholder="用途說明">
                        </div>
                        <button class="btn btn-success" onclick="createApiKey()">創建 API Key</button>
                    </div>
                    
                    <!-- API Keys 列表 -->
                    <h4>您的 API Keys</h4>
                    <div id="api-keys-list" class="loading">載入中...</div>
                </div>
                
                <!-- GA4 屬性管理 -->
                <div id="properties-tab" class="tab-content">
                    <h3>GA4 屬性管理</h3>
                    
                    <!-- 添加新屬性 -->
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h4>添加 GA4 屬性</h4>
                        <div class="form-group">
                            <label class="form-label">GA4 屬性 ID</label>
                            <input type="text" class="form-input" id="property-id" placeholder="例如：123456789">
                        </div>
                        <div class="form-group">
                            <label class="form-label">屬性名稱</label>
                            <input type="text" class="form-input" id="property-name" placeholder="例如：我的網站">
                        </div>
                        <button class="btn btn-success" onclick="addProperty()">添加屬性</button>
                    </div>
                    
                    <!-- 屬性列表 -->
                    <h4>您的 GA4 屬性</h4>
                    <div id="properties-list" class="loading">載入中...</div>
                </div>
                
                <!-- 文檔頁籤 -->
                <div id="docs-tab" class="tab-content">
                    <h3>API 文檔與測試</h3>
                    <p>使用以下資源開始使用 API：</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="/docs" class="btn btn-success" target="_blank">📖 完整 API 文檔</a>
                        <a href="/health" class="btn" target="_blank">🔧 系統狀態</a>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-top: 20px;">
                        <h4>快速測試</h4>
                        <p>使用您的 API Key 測試端點：</p>
                        <div style="background: #2d3748; color: #e2e8f0; padding: 15px; border-radius: 6px; margin: 10px 0;">
                            <code>curl -H "X-API-Key: your_api_key" http://localhost:8002/active-users</code>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // 頁籤切換
            function showTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                document.querySelectorAll('.tab-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                
                document.getElementById(tabName + '-tab').classList.add('active');
                event.target.classList.add('active');
                
                if (tabName === 'api-keys') {
                    loadApiKeys();
                } else if (tabName === 'properties') {
                    loadProperties();
                }
            }
            
            // 載入 API Keys
            async function loadApiKeys() {
                document.getElementById('api-keys-list').innerHTML = '<div class="loading">載入中...</div>';
                
                try {
                    const response = await fetch('/api/user/api-keys');
                    if (!response.ok) throw new Error('載入失敗');
                    
                    const data = await response.json();
                    
                    if (data.api_keys && data.api_keys.length > 0) {
                        let html = '';
                        data.api_keys.forEach(key => {
                            html += `
                                <div class="api-key-item">
                                    <div class="api-key-info">
                                        <div class="api-key-name">${key.name}</div>
                                        <div class="api-key-value">${key.key}</div>
                                        <small style="color: #666;">創建時間: ${new Date(key.created_at).toLocaleDateString()}</small>
                                    </div>
                                    <div>
                                        <button class="btn btn-danger" onclick="deleteApiKey(${key.id})">刪除</button>
                                    </div>
                                </div>
                            `;
                        });
                        document.getElementById('api-keys-list').innerHTML = html;
                    } else {
                        document.getElementById('api-keys-list').innerHTML = '<p style="text-align: center; color: #666;">尚無 API Keys，請創建一個</p>';
                    }
                } catch (error) {
                    document.getElementById('api-keys-list').innerHTML = '<div class="error">載入失敗，請重試</div>';
                }
            }
            
            // 創建 API Key
            async function createApiKey() {
                const name = document.getElementById('api-key-name').value.trim();
                const description = document.getElementById('api-key-description').value.trim();
                
                if (!name) {
                    alert('請輸入 API Key 名稱');
                    return;
                }
                
                try {
                    const response = await fetch('/api/user/api-keys', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ name, description })
                    });
                    
                    if (!response.ok) throw new Error('創建失敗');
                    
                    document.getElementById('api-key-name').value = '';
                    document.getElementById('api-key-description').value = '';
                    loadApiKeys();
                    alert('✅ API Key 創建成功！');
                } catch (error) {
                    alert('❌ 創建失敗，請重試');
                }
            }
            
            // 刪除 API Key
            async function deleteApiKey(keyId) {
                if (!confirm('確定要刪除這個 API Key 嗎？')) return;
                
                try {
                    const response = await fetch(`/api/user/api-keys/${keyId}`, {
                        method: 'DELETE'
                    });
                    
                    if (!response.ok) throw new Error('刪除失敗');
                    
                    loadApiKeys();
                    alert('✅ API Key 已刪除');
                } catch (error) {
                    alert('❌ 刪除失敗，請重試');
                }
            }
            
            // 載入屬性 (占位符)
            function loadProperties() {
                document.getElementById('properties-list').innerHTML = '<p style="text-align: center; color: #666;">屬性管理功能開發中...</p>';
            }
            
            // 添加屬性 (占位符)
            function addProperty() {
                alert('屬性管理功能開發中...');
            }
            
            // 頁面載入時執行
            document.addEventListener('DOMContentLoaded', function() {
                loadApiKeys();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=dashboard_html)

# API Key 管理端點
@router.post("/api/user/api-keys")
async def create_user_api_key(
    request: CreateApiKeyRequest,
    db: AsyncSession = Depends(get_db)
):
    """創建用戶 API Key"""
    try:
        # 生成 API Key
        def generate_api_key():
            return f"ga4_{secrets.token_urlsafe(32)}"
        
        # 創建 API Key 記錄
        new_key = UserApiKey(
            user_id=1,  # 暫時使用固定用戶 ID
            key_name=request.name,
            description=request.description,
            api_key=generate_api_key(),
            property_id=None,  # 暫時設為 None，因為 property_id 是外鍵
            is_active=True
        )
        
        db.add(new_key)
        await db.commit()
        await db.refresh(new_key)
        
        return {
            "success": True,
            "message": "API Key 創建成功",
            "api_key": {
                "id": new_key.id,
                "name": new_key.key_name,
                "key": new_key.api_key,
                "created_at": new_key.created_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"創建 API Key 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="創建 API Key 失敗"
        )

@router.get("/api/user/api-keys")
async def get_user_api_keys(
    db: AsyncSession = Depends(get_db)
):
    """獲取用戶的 API Keys"""
    try:
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == 1,  # 暫時使用固定用戶 ID
                UserApiKey.is_active == True
            ).order_by(UserApiKey.created_at.desc())
        )
        api_keys = result.scalars().all()
        
        return {
            "success": True,
            "api_keys": [
                {
                    "id": key.id,
                    "name": key.key_name,
                    "description": key.description,
                    "key": key.api_key,
                    "property_id": key.property_id,
                    "created_at": key.created_at.isoformat(),
                    "is_active": key.is_active
                }
                for key in api_keys
            ]
        }
        
    except Exception as e:
        logger.error(f"獲取 API Keys 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="獲取 API Keys 失敗"
        )

@router.delete("/api/user/api-keys/{key_id}")
async def delete_user_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db)
):
    """刪除用戶 API Key"""
    try:
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.id == key_id,
                UserApiKey.user_id == 1,  # 暫時使用固定用戶 ID
                UserApiKey.is_active == True
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API Key 不存在"
            )
        
        # 軟刪除
        api_key.is_active = False
        api_key.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "message": "API Key 已刪除"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除 API Key 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刪除 API Key 失敗"
        ) 