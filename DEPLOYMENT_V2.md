# GA4 API Service V2 部署指南

## 🚀 Version 2 新功能

Version 2 是 GA4 API Service 的重大升級，支援：

### 🔐 雙模式認證
- **API Key 模式**：向後兼容 V1，適合內部團隊使用
- **OAuth 模式**：支援多租戶，用戶可連接自己的 GA4 帳號

### 🗄️ 資料庫支援
- PostgreSQL 資料庫存儲用戶資料
- OAuth token 自動管理和刷新
- API 使用記錄和分析

### 📊 增強功能
- 用戶可管理多個 GA4 屬性
- 詳細的 API 使用統計
- 更完整的錯誤處理和日誌

---

## 📋 部署需求

### 基礎需求
- Python 3.11+
- PostgreSQL 資料庫（Railway 自動提供）
- Google Cloud Console 專案

### Google Cloud 設定
1. **啟用 API**：
   - Google Analytics Data API
   - Google Analytics Admin API
   
2. **OAuth 2.0 設定**（新增）：
   ```
   授權的重新導向 URI:
   https://your-app.railway.app/auth/callback
   ```

---

## ⚙️ 環境變數配置

### V1 兼容變數（保留）
```bash
# GA4 配置
GA4_PROPERTY_ID=319075120
SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# API Keys (V1 兼容)
API_KEY_JOEY=abc123def456
API_KEY_TINA=xyz789uvw012
API_KEY_ADMIN=admin_secret_key_2023
```

### V2 新增變數
```bash
# OAuth 配置
GOOGLE_CLIENT_ID=your_client_id.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=https://your-app.railway.app/auth/callback
BASE_URL=https://your-app.railway.app

# 資料庫（Railway 自動設定）
DATABASE_URL=postgresql://user:password@host:port/database

# 功能開關
ENABLE_OAUTH_MODE=true
ENABLE_API_KEY_MODE=true
```

---

## 🚀 Railway 部署步驟

### 1. 資料庫設定
在 Railway 專案中添加 PostgreSQL 服務：
```bash
# Railway 會自動設定 DATABASE_URL
```

### 2. 環境變數設定
在 Railway Dashboard 設定所有必要的環境變數

### 3. 部署設定
更新 `railway.json`：
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn main_v2:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 4. 初始化資料庫
部署後執行：
```bash
python init_db.py init
```

---

## 🔧 本地開發設定

### 1. 安裝依賴
```bash
# 使用 uv（推薦）
uv pip install -r requirements.txt

# 或使用 pip
pip install -r requirements.txt
```

### 2. 設定環境變數
複製 `env-example.txt` 為 `.env`，並填入正確的值

### 3. 啟動本地資料庫（可選）
```bash
# 使用 Docker
docker run --name ga4-postgres -e POSTGRES_PASSWORD=password -p 5432:5432 -d postgres:15

# 設定本地 DATABASE_URL
DATABASE_URL=postgresql://postgres:password@localhost:5432/postgres
```

### 4. 初始化資料庫
```bash
python init_db.py init
```

### 5. 啟動服務
```bash
# V2 版本
uvicorn main_v2:app --reload --port 8000

# V1 版本（兼容）
uvicorn main:app --reload --port 8001
```

---

## 📖 API 使用指南

### 🔐 API Key 認證（V1 兼容）
```bash
curl -H "X-API-Key: abc123def456" \
     http://localhost:8000/active-users
```

響應格式（V1 兼容）：
```json
{
  "user": "joey",
  "activeUsers": 1665,
  "timestamp": "2023-12-15T10:30:00Z",
  "status": "success"
}
```

### 🔐 OAuth 認證（新功能）

#### 1. 獲取授權 URL
```bash
curl http://localhost:8000/auth/google
```

響應：
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "random_state_string",
  "message": "請在瀏覽器中打開授權 URL 並完成授權"
}
```

#### 2. 用戶完成授權
用戶在瀏覽器中完成 Google OAuth 流程

#### 3. 使用 Bearer Token 存取 API
```bash
curl -H "Authorization: Bearer ya29.a0Ae4lv..." \
     http://localhost:8000/active-users
```

響應格式（V2 增強）：
```json
{
  "user": "user@example.com",
  "user_type": "oauth",
  "activeUsers": 1665,
  "property_id": "123456789",
  "timestamp": "2023-12-15T10:30:00Z",
  "status": "success"
}
```

#### 4. 查看用戶資訊
```bash
curl -H "Authorization: Bearer ya29.a0Ae4lv..." \
     http://localhost:8000/user/info
```

---

## 🧪 測試

### 自動化測試
```bash
# 執行 V2 測試套件
python test_v2_api.py

# 資料庫測試
python init_db.py test
```

### 手動測試檢查清單
- [ ] 健康檢查端點 (`/health`)
- [ ] API Key 認證正常運作
- [ ] OAuth 授權流程正常
- [ ] 資料庫連接正常
- [ ] 雙模式可同時運作

---

## 📊 監控和日誌

### 應用日誌
```bash
# 查看 Railway 日誌
railway logs

# 本地查看日誌
tail -f app.log
```

### 資料庫管理
```bash
# 查看資料庫狀態
python init_db.py info

# 重置資料庫（危險操作）
python init_db.py reset
```

### API 使用統計
V2 版本自動記錄所有 API 使用情況到 `api_usage_logs` 表

---

## 🔄 從 V1 遷移

### 零停機遷移策略
1. 部署 V2 版本到新的 Railway 服務
2. 配置相同的 API Keys 保持兼容性
3. 測試 V1 功能在 V2 中正常運作
4. 逐步將流量切換到 V2
5. 啟用 OAuth 功能供新用戶使用

### 配置遷移
- V1 的所有環境變數在 V2 中保持兼容
- API Key 用戶無需任何更改
- 所有 V1 端點在 V2 中正常運作

---

## ⚠️ 注意事項

### 安全考量
- 確保 `GOOGLE_CLIENT_SECRET` 保密
- 定期輪換 API Keys
- 監控異常的 API 使用

### 效能考量
- 資料庫連接池已最佳化
- OAuth token 自動刷新避免過期
- 速率限制防止濫用

### 擴展建議
- 設定 Redis 用於分散式速率限制
- 實施 API 使用配額管理
- 添加更多 GA4 分析端點

---

## 🆘 故障排除

### 常見問題

**Q: OAuth 模式無法啟動**
A: 檢查 `GOOGLE_CLIENT_ID` 和 `GOOGLE_CLIENT_SECRET` 是否正確設定

**Q: 資料庫連接失敗**
A: 確認 Railway PostgreSQL 服務正常運行，`DATABASE_URL` 正確

**Q: API Key 認證失敗**
A: 檢查環境變數格式：`API_KEY_[USERNAME]=key`

**Q: Token 過期錯誤**
A: V2 會自動刷新過期的 token，如果持續失敗請重新授權

### 調試模式
```bash
# 啟用詳細日誌
export LOG_LEVEL=DEBUG
uvicorn main_v2:app --reload
```

---

## 📞 支援

如有問題請檢查：
1. Railway 部署日誌
2. 資料庫連接狀態
3. Google Cloud Console 配置
4. 環境變數設定

完整的測試和監控確保 V2 版本穩定可靠！ 