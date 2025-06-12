# GA4 Realtime API Integration - Product Requirements Document (PRD)

## 🧭 Context & Background

BlockTempo 希望將 Google Analytics 4 (GA4) 的即時在線人數（`activeUsers`）資料，整合至內部應用與自動化流程中，例如：

- n8n 定時自動拉取 GA4 數據
- 在 Telegram、Notion、報表系統中動態顯示
- 為後續多租戶平台（如 SaaS 查詢面板）鋪路

### ✅ 今日需求分析與開發討論背景：

- 使用者為 BlockTempo 內部團隊與管理人員
- GA4 的查詢需求為單一帳戶，但多人分權使用
- FastAPI 部署使用 Railway，需快速上線且可擴充
- GA4 API 權限目前採用 Service Account 模式（已授權 Viewer）
- n8n 無法使用 OAuth2 Credential 節點直接查 GA4 Realtime API，因此改由自建 API 中介服務解法

經過技術驗證，確認如下限制：

- GA4 Realtime API (`runRealtimeReport`) **不支援 API Key，只接受 OAuth2/Service Account 認證**
- n8n HTTP 節點無法直接綁定 Google OAuth2 Credential
- Service Account 是最適合單租戶、非登入型場景的 OAuth 替代方案

---

## 📄 Overview

本文件定義一個 FastAPI 架構的 GA4 Realtime 整合服務，提供兩種版本設計：

1. **單租戶版本**：僅查詢 BlockTempo 自家 GA4 資料，支援 API Key 安全驗證
2. **多租戶版本**：支援讓不同使用者連接各自 GA4 Property，需完整 OAuth 授權、Token 管理

---

## ✅ Version 1: 單租戶 + 多人使用 + API Key 安全保護（推薦起手式）

### 🎯 使用情境

BlockTempo 團隊內部成員可經由 API Key 查詢「同一個 GA4 帳號」的即時在線人數。例：

- Joey 查自己站的數據
- 行銷團隊自動用 n8n 拉數據製作報表

### 🛠 技術架構

- FastAPI (Python)
- Railway 部署
- Google Analytics Data API (v1beta)
- GA4 Service Account JSON 金鑰
- 多組 API Key 寫於 Railway 環境變數

### 🔐 安全驗證設計

- 所有請求必須帶 `X-API-Key`
- 支援多組 API Key（使用者辨識）
- API Key 儲存在 Railway Environment Variables，不寫死在程式

### 🧾 API 定義

**GET** `/active-users`

#### Request Header：

```
X-API-Key: abc123
```

#### Response 範例：

```json
{
  "user": "Joey",
  "activeUsers": 1665
}
```

### 📦 Railway 設定

**Environment Variables**：

```
API_KEY_JOEY=abc123
API_KEY_TINA=xyz789
GA4_PROPERTY_ID=123456789
```

> `service-account.json` 可透過 GitHub ignore 或手動上傳保持隱私

### 🧠 實作細節

- 使用 `google.oauth2.service_account` 模組於每次請求產生 token
- 所有 token 為 short-lived（1 小時），但可透過金鑰動態刷新
- 不需資料庫即可管理多人 API 權限

---

## ✅ Version 2: 多租戶 SaaS 架構 - OAuth2 + 資料庫（擴充用）

### 🎯 使用情境

若日後將此查詢平台提供給其他合作方，或不同帳號的人要查「自己的 GA4 資料」，則需支援 OAuth 授權流程。例：

- 每個用戶連接自己的 GA4 帳號
- 查詢的是該用戶的 activeUsers 數據

### 🛠 技術架構

- FastAPI + Railway + PostgreSQL
- Google OAuth2 登入與授權流程
- Token 儲存與刷新邏輯（access + refresh）
- 使用者 + Token 關聯 DB 設計

### 🔐 安全流程

- 使用者登入時跳轉 Google OAuth
- 選擇 GA4 權限後授權應用
- 存下 token + GA4 property ID
- 之後每次呼叫時根據用戶身份動態帶入對應 token 查詢

### 📄 API 設計

#### `GET /auth/google`

- 啟動 OAuth 授權流程

#### `GET /callback`

- Google redirect 回來，存 access/refresh token

#### `GET /active-users`

- 帶 OAuth Bearer token 查該使用者綁定的 GA4 Property activeUsers

### 🗄 DB Schema 建議

```sql
users (id, email, ga_property_id)
oauth_tokens (user_id, access_token, refresh_token, expires_at)
```

### 📦 Railway 設定

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `DATABASE_URL`
- `OAUTH_REDIRECT_URI`

### ⚙️ 實作備註

- 需實作自動 token refresh（用 refresh\_token 換新的 access\_token）
- 可支援多個 GA4 帳號綁定 / 切換
- 預留未來設定 GA View、Filter、日期區間等功能

---

## 🚀 Rollout 建議

| 階段      | 內容                                                 |
| ------- | -------------------------------------------------- |
| Phase 1 | 優先建置單租戶 API（使用 Service Account + API Key）以快速支援內部需求 |
| Phase 2 | 若有多帳號、多 GA4 管理需求，再擴展至多租戶 OAuth 架構                  |

---

## ✅ 總結

| 功能面向    | 單租戶版本                  | 多租戶版本                            |
| ------- | ---------------------- | -------------------------------- |
| GA 授權   | Service Account (固定金鑰) | 使用者 OAuth 授權 + token refresh     |
| 安全驗證    | 多組 API Key in env      | OAuth2 Bearer Token + User ID 驗證 |
| 使用者存取控制 | 靜態映射                   | 動態查詢 + 資料庫管理                     |
| 適用場景    | 內部自用（n8n、自動化）          | 提供外部使用者或部門自主查詢                   |

---

> 建議先實作 Version 1，能最快速支援內部需求，後續再根據實際擴充情境推進 Version 2。

