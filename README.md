# GA4 Realtime API Service

BlockTempo GA4 即時在線人數查詢服務

## 🚀 快速部署 (Railway)

1. **Fork 此專案到您的 GitHub**

2. **連接到 Railway**
   - 登入 [Railway](https://railway.app)
   - 選擇 "Deploy from GitHub repo"
   - 選擇此專案

3. **設定環境變數**
   ```bash
   GA4_PROPERTY_ID=你的GA4屬性ID
   SERVICE_ACCOUNT_JSON=你的Service Account JSON內容
   API_KEY_JOEY=joey的API密鑰
   API_KEY_TINA=tina的API密鑰
   ```

4. **部署完成**
   - Railway會自動偵測Python專案並部署
   - 部署後會獲得一個公用URL

## 📡 API 使用方法

### 🔥 實時數據查詢

#### 即時在線人數
```bash
curl -X GET "https://your-app.railway.app/active-users" \
  -H "X-API-Key: abc123def456"
```

#### 實時總覽數據
```bash
curl -X GET "https://your-app.railway.app/realtime/overview" \
  -H "X-API-Key: abc123def456"
```

#### 實時熱門頁面
```bash
curl -X GET "https://your-app.railway.app/realtime/top-pages?limit=10" \
  -H "X-API-Key: abc123def456"
```

### 📊 分析數據查詢

#### 流量來源分析
```bash
curl -X GET "https://your-app.railway.app/analytics/traffic-sources?start_date=7daysAgo&end_date=today" \
  -H "X-API-Key: abc123def456"
```

#### 頁面瀏覽分析
```bash
curl -X GET "https://your-app.railway.app/analytics/pageviews?start_date=7daysAgo&end_date=today" \
  -H "X-API-Key: abc123def456"
```

#### 設備分析
```bash
curl -X GET "https://your-app.railway.app/analytics/devices?start_date=7daysAgo&end_date=today" \
  -H "X-API-Key: abc123def456"
```

#### 地理位置數據
```bash
curl -X GET "https://your-app.railway.app/analytics/geographic?start_date=7daysAgo&end_date=today" \
  -H "X-API-Key: abc123def456"
```

#### 熱門頁面詳細分析 (包含完整URL)
```bash
curl -X GET "https://your-app.railway.app/analytics/top-pages?start_date=1daysAgo&end_date=today&limit=10" \
  -H "X-API-Key: abc123def456"
```

#### 站內搜索分析
```bash
curl -X GET "https://your-app.railway.app/analytics/search-terms?start_date=7daysAgo&end_date=today&limit=20" \
  -H "X-API-Key: abc123def456"
```

#### 頁面效能分析
```bash
curl -X GET "https://your-app.railway.app/analytics/performance?start_date=7daysAgo&end_date=today&limit=20" \
  -H "X-API-Key: abc123def456"
```

### 回應格式範例

#### 即時在線人數
```json
{
  "user": "joey",
  "activeUsers": 1665,
  "timestamp": "2023-12-07T10:30:00.123456",
  "status": "success"
}
```

#### 實時總覽
```json
{
  "user": "joey",
  "data": {
    "activeUsers": 1665,
    "pageViews": 2341,
    "events": 5672,
    "topCountries": [
      {"name": "Taiwan", "users": 892},
      {"name": "United States", "users": 445}
    ],
    "deviceBreakdown": [
      {"name": "desktop", "users": 1203},
      {"name": "mobile", "users": 462}
    ]
  },
  "timestamp": "2023-12-07T10:30:00.123456",
  "status": "success"
}
```

### 🔍 系統監控

#### 健康檢查
```bash
curl https://your-app.railway.app/health
```

#### API文檔
```bash
# Swagger UI
https://your-app.railway.app/docs

# ReDoc
https://your-app.railway.app/redoc
```

## 🔧 本地開發

```bash
# 安裝依賴
pip install -r requirements.txt

# 設定環境變數
cp env-example.txt .env
# 編輯 .env 檔案

# 啟動服務
uvicorn main:app --reload
```

API文檔: http://localhost:8000/docs

## 🔐 Service Account 設定

1. 前往 [Google Cloud Console](https://console.cloud.google.com)
2. 建立或選擇專案
3. 啟用 Google Analytics Reporting API
4. 建立 Service Account
5. 下載 JSON 金鑰
6. 在 GA4 中授予該 Service Account 查看者權限

## ⚡ 功能特色

### 🔐 安全與認證
- ✅ API Key 多用戶驗證
- ✅ 速率限制保護 (每10分鐘200次)
- ✅ Service Account 安全整合

### 📊 數據查詢功能
- ✅ **實時數據**: 在線用戶、熱門頁面、流量總覽
- ✅ **歷史分析**: 頁面瀏覽、流量來源、用戶行為
- ✅ **設備分析**: 設備類型、作業系統、瀏覽器統計
- ✅ **地理數據**: 國家/城市分布、地理流量分析
- ✅ **自定義日期範圍**: 支援靈活的查詢期間

### 🛠 技術特色
- ✅ 現代化 uv 套件管理
- ✅ FastAPI + Swagger 自動文檔
- ✅ 結構化日誌記錄
- ✅ 健康檢查端點
- ✅ 完整的錯誤處理機制
- ✅ Railway 部署就緒

### 🎯 使用場景
- ✅ n8n 自動化整合
- ✅ 即時儀表板顯示
- ✅ Telegram/Notion 通知
- ✅ 數據分析報表
- ✅ 流量監控警報 