# GA4 Realtime API Service

BlockTempo GA4 即時在線人數查詢服務

## 🚀 快速部署 (Railway)

1. **Fork 此專案到您的 GitHub**

2. **連接到 Railway**
   - 登入 [Railway](https://railway.app)
   - 點擊 "New Project" → "Deploy from GitHub repo"
   - 選擇此專案倉庫
   - Railway 會自動檢測並部署

3. **設定環境變數**
   在 Railway Dashboard 中添加以下環境變數：
   ```bash
   GA4_PROPERTY_ID=你的GA4屬性ID
   GOOGLE_SERVICE_ACCOUNT_JSON=你的Service Account JSON內容(單行格式)
   API_KEYS=你的API密鑰(逗號分隔)
   RATE_LIMIT_REQUESTS=200
   RATE_LIMIT_WINDOW_MINUTES=10
   ```

4. **自動部署**
   - 每次 push 到 main 分支會自動觸發部署
   - Railway 會自動檢測 `railway.json` 配置
   - 部署完成後獲得公用 URL

### 🔒 部署安全性說明

**✅ V2開發不會影響現有服務**

Railway 部署配置 (`railway.json`) 明確指定：
```json
{
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT"
  }
}
```

- Railway **僅啟動 V1版本** (`main:app`)
- 即使提交 V2 程碼到 GitHub，**現有 V1 服務完全不受影響**
- V2 程碼可以安全地進行開發和測試
- 要部署 V2 需要手動修改 `railway.json` 的 `startCommand`

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

#### 單篇頁面詳細分析 ⭐ 新功能
```bash
# 使用頁面路徑查詢
curl -X GET "https://your-app.railway.app/analytics/single-page?page_path=/article-title/&start_date=7daysAgo&end_date=today" \
  -H "X-API-Key: abc123def456"

# 使用完整URL查詢  
curl -X GET "https://your-app.railway.app/analytics/single-page?page_path=https://example.com/article-title/&start_date=yesterday&end_date=today" \
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

#### 單篇頁面分析
```json
{
  "user": "joey",
  "pageData": {
    "pagePath": "/iran-bans-crypto-night/",
    "pageTitle": "伊朗宣布「晚上禁用加密貨幣」，以色列駭客燒毀Nobitex 1億美元引爆鏈上恐慌火",
    "dateRange": "7daysAgo to today",
    "summary": {
      "totalPageViews": 4832,
      "totalUsers": 3654,
      "totalSessions": 4121,
      "newUsers": 2891,
      "avgBounceRate": 8.23,
      "avgEngagementRate": 91.77,
      "avgSessionDuration": 156.45,
      "performanceGrade": "A+ (優秀)"
    },
    "dailyBreakdown": [
      {
        "date": "20250613",
        "pageViews": 687,
        "users": 523,
        "sessions": 612,
        "avgSessionDuration": 142.31,
        "bounceRate": 7.84,
        "engagementRate": 92.16,
        "newUsers": 445
      }
    ],
    "trafficSources": [
      {
        "channelGroup": "Organic Search",
        "source": "google",
        "medium": "organic", 
        "sessions": 2341,
        "users": 1876,
        "pageViews": 2587
      }
    ],
    "deviceBreakdown": [
      {
        "deviceCategory": "mobile",
        "operatingSystem": "Android",
        "users": 2134,
        "sessions": 2398,
        "pageViews": 2756
      }
    ]
  },
  "timestamp": "2025-06-19T10:30:00.123456",
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

## 🔧 本地開發與測試

### 📋 專案版本說明

此專案包含兩個版本：

- **V1版本 (Production)**: `main.py` - 端口 8000 - 目前Railway部署版本
- **V2版本 (Development)**: `main_v2.py` - 端口 8002 - 新功能開發版本

### 🛠 環境設置

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 設定環境變數
cp env-example.txt .env

# 3. 編輯 .env 文件，至少需要設置：
# GA4_PROPERTY_ID=你的GA4屬性ID
# SERVICE_ACCOUNT_JSON=你的服務帳戶JSON
# API_KEY_JOEY=你的API金鑰
```

### 🧪 V1版本測試 (Production Version)

```bash
# 啟動V1服務
python main.py
# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 使用測試腳本
python test_api.py http://localhost:8000 你的API金鑰

# 手動測試
curl http://localhost:8000/health
curl -X GET "http://localhost:8000/active-users" -H "X-API-Key: 你的API金鑰"
```

**V1 API文檔**: http://localhost:8000/docs

### 🧪 V2版本測試 (Development Version)

```bash
# 1. 初始化V2資料庫
python init_db.py

# 2. 啟動V2服務
python main_v2.py
# 或使用 uvicorn
uvicorn main_v2:app --reload --host 0.0.0.0 --port 8002

# 3. 使用V2專用測試腳本
python test_v2_api.py

# 4. 手動測試V2新功能
curl http://localhost:8002/health
curl http://localhost:8002/dashboard  # 用戶控制面板
curl http://localhost:8002/auth/google  # OAuth認證
```

**V2 API文檔**: http://localhost:8002/docs

### 🔄 同時運行兩個版本

你可以同時運行V1和V2進行功能比較：

```bash
# 終端1 - 啟動V1
python main.py
# 服務運行在 http://localhost:8000

# 終端2 - 啟動V2  
python main_v2.py
# 服務運行在 http://localhost:8002

# 終端3 - 執行比較測試
python test_api.py http://localhost:8000 你的API金鑰     # 測試V1
python test_v2_api.py                                    # 測試V2
```

### 📊 版本功能比較

| 功能 | V1版本 | V2版本 |
|------|--------|--------|
| GA4數據查詢 | ✅ | ✅ |
| API Key認證 | ✅ | ✅ |
| OAuth 2.0認證 | ❌ | ✅ |
| 用戶管理面板 | ❌ | ✅ |
| 資料庫支持 | ❌ | ✅ |
| API Key管理 | ❌ | ✅ |
| 速率限制 | ✅ | ✅ |

### 🐛 除錯技巧

```bash
# 檢查環境變數載入
python debug_env.py

# 檢查V2資料庫狀態
python -c "
from database import test_database_connection
import asyncio
asyncio.run(test_database_connection())
"

# 查看所有API Keys
env | grep API_KEY_

# 測試新的單篇頁面分析功能
python test_single_page.py http://localhost:8000 你的API金鑰 /article-path/
```

### 🆕 新功能測試

**單篇頁面分析功能**：
```bash
# 測試正式環境
python test_single_page.py https://ga4.blocktempo.ai 你的API金鑰 /iran-bans-crypto-night/

# 測試本地開發環境
python test_single_page.py http://localhost:8000 你的API金鑰 /article-path/

# 使用完整URL測試
python test_single_page.py https://ga4.blocktempo.ai 你的API金鑰 "https://www.blocktempo.com/some-article/"
```

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
- ✅ **單篇頁面分析**: ⭐ 查詢特定文章的詳細數據和趨勢
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
