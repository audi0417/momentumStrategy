# Momentum Stocks Web Dashboard

互動式股票動能分析儀表板，提供K線圖和技術指標分析。

## 功能特色

- 📊 **動能股票表格** - 顯示歷史動能分數，預留未來日期欄位
- 📈 **互動式K線圖** - 90天股價走勢，包含成交量
- 📉 **技術指標** - MACD和RSI分析
- 🎨 **響應式設計** - 固定佈局，適應各種螢幕尺寸
- ⚡ **即時數據** - 使用yfinance獲取最新股價

## 本地運行

### 前置要求
- Python 3.8+
- 虛擬環境

### 安裝步驟

1. **設置虛擬環境**
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate     # Windows
```

2. **安裝依賴**
```bash
pip install -r ../requirements.txt
```

3. **啟動服務器**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

4. **訪問應用**
打開瀏覽器：http://localhost:8000

## 文件結構

```
web/
├── index.html     # 主頁面
├── style.css      # 樣式文件
├── script.js      # 前端邏輯
├── main.py        # FastAPI後端
├── demo.html      # 靜態演示版本
└── README.md      # 說明文件
```

## API端點

- `GET /` - 主頁面
- `GET /api/data` - 獲取動能數據
- `GET /api/kline/{stock_id}` - K線圖數據
- `GET /api/indicators/{stock_id}` - 技術指標數據

## 技術棧

- **前端**: HTML5, CSS3, JavaScript, Plotly.js
- **後端**: FastAPI, Python
- **數據**: yfinance, pandas, numpy
- **圖表**: Plotly (互動式圖表)

## 部署說明

### GitHub Pages (靜態版本)
- 只能顯示界面設計
- 無法獲取即時數據
- 訪問: `demo.html`

### 完整部署
需要支援Python的服務器：
- Heroku
- Railway
- DigitalOcean
- AWS EC2

## 開發團隊

🤖 Generated with [Claude Code](https://claude.ai/code)