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

### 取得即時在線人數

```bash
curl -X GET "https://your-app.railway.app/active-users" \
  -H "X-API-Key: abc123def456"
```

### 回應格式

```json
{
  "user": "joey",
  "activeUsers": 1665,
  "timestamp": "2023-12-07T10:30:00.123456",
  "status": "success"
}
```

### 健康檢查

```bash
curl https://your-app.railway.app/health
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

- ✅ API Key 多用戶驗證
- ✅ 速率限制保護 (每10分鐘200次)
- ✅ 結構化日誌記錄
- ✅ 健康檢查端點
- ✅ Swagger API 文檔
- ✅ 錯誤處理機制 