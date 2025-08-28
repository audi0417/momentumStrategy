# 台股動能選股系統

## 專案概述

自動化台股篩選系統，根據動能、RSI 和 MACD 等技術指標篩選出具有投資潛力的股票。系統每個工作日自動運行，並通過電子郵件發送篩選結果。

## 功能特點

- **多重指標篩選**：結合動能、RSI 和 MACD 等多種技術指標
- **自動化執行**：透過 GitHub Actions 在每個工作日自動運行
- **歷史追蹤**：記錄並追蹤股票信號持續的天數
- **電子郵件通知**：自動發送篩選結果到指定郵箱
- **智能交易日判斷**：自動辨識假日和非交易日

## 篩選條件

系統使用以下標準篩選股票：

1. **動能篩選**：短期價格變化超過 7%
2. **RSI 信號**：使用 5 日和 80 日 RSI 指標產生買入信號
3. **MACD 信號**：使用標準 MACD 參數 (12, 26, 9) 產生買入信號
4. **成交量門檻**：成交量超過 5 億元

## 系統架構

```
├── .github/workflows  - GitHub Actions 工作流配置
│   └── python-app.yml
├── requirements.txt   - 依賴套件清單
├── stocks_data.json   - 股票歷史數據和信號記錄
└── 動能選股.py         - 主程序文件
```

## 安裝與使用

### 前置需求

- Python 3.x
- 必要的 Python 套件 (可通過 requirements.txt 安裝)

### 本地安裝步驟

1. 克隆儲存庫：
   ```bash
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name
   ```

2. 安裝依賴：
   ```bash
   pip install -r requirements.txt
   ```

3. 設定環境變數：
   ```bash
   export SENDER_EMAIL="your-email@gmail.com"
   export APP_PASSWORD="your-app-password"
   export RECIVER_EMAIL="recipient-email@example.com"
   # 多個收件者請用逗號分隔：
   # export RECIVER_EMAIL="email1@example.com,email2@example.com,email3@example.com"
   ```

4. 運行程式：
   ```bash
   python 動能選股.py
   ```

### GitHub Actions 自動化設定

要使用 GitHub Actions 自動運行，請設定以下 secrets：

- `SENDER_EMAIL`: 用於發送郵件的 Gmail 帳號
- `APP_PASSWORD`: Gmail 的應用程式密碼
- `RECIVER_EMAIL`: 接收結果的信箱地址（多個收件者請用逗號分隔，例如：email1@example.com,email2@example.com）
- `TOKEN`: GitHub 個人訪問令牌 (用於提交更新後的 stocks_data.json)

## 輸出結果說明

每次運行後，系統將生成包含以下內容的電子郵件報告：

1. **動能選股**：列出動能指標大於 7% 的股票
2. **RSI 選股**：列出符合 RSI 信號的股票
3. **MACD 選股**：列出符合 MACD 信號的股票
4. **最終篩選結果**：同時符合上述所有條件的股票

每支符合條件的股票會顯示其代號、名稱、動能值、成交量和連續出現信號的天數。

## 注意事項

- 系統預設每個工作日台灣時間早上 5:00 自動運行
- 使用 Gmail 發送郵件時需要設定應用程式密碼
- 績效和交易決策應由使用者自行評估和決定

## 免責聲明

本專案僅供學習和研究用途，不構成任何投資建議。使用者應自行承擔使用本系統所產生的風險。股市有風險，投資需謹慎。
