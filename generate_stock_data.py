import json
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

def generate_stock_data():
    """生成股票歷史數據並儲存為JSON"""
    
    # 讀取動能數據來獲取股票列表
    with open('historical_data.json', 'r', encoding='utf-8') as f:
        momentum_data = json.load(f)
    
    # 讀取股票元數據
    metadata = {}
    if os.path.exists('stock_metadata.json'):
        with open('stock_metadata.json', 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    
    # 獲取所有股票代號
    all_stocks = set()
    for date_data in momentum_data['dates'].values():
        all_stocks.update(date_data.keys())
    
    print(f"找到 {len(all_stocks)} 隻股票")
    
    # 儲存股票價格數據的字典
    stock_price_data = {}
    
    # 設定日期範圍（過去120天）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)
    
    all_stocks_list = list(all_stocks)
    total_stocks = len(all_stocks_list)
    
    for i, stock_id in enumerate(all_stocks_list):  # 處理所有股票
        print(f"處理股票 {stock_id} ({i+1}/{total_stocks})")
        
        try:
            # 嘗試不同的股票代號後綴
            data = None
            ticker_symbols_to_try = []
            
            # 根據metadata判斷市場類型
            market_type = metadata.get(stock_id, '上市')
            if market_type == '上櫃':
                ticker_symbols_to_try = [f"{stock_id}.TWO", f"{stock_id}.TW"]
            else:
                ticker_symbols_to_try = [f"{stock_id}.TW", f"{stock_id}.TWO"]
            
            # 嘗試不同的代號
            for ticker_symbol in ticker_symbols_to_try:
                try:
                    print(f"  - 嘗試 {ticker_symbol}")
                    temp_data = yf.download(ticker_symbol, start=start_date, end=end_date)
                    if not temp_data.empty:
                        data = temp_data
                        print(f"  ✓ 成功使用 {ticker_symbol}")
                        break
                except:
                    continue
            
            if data is None or data.empty:
                print(f"  - 無法獲取 {stock_id} 的數據（已嘗試所有後綴）")
                continue
            
            # 處理多層索引
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns.values]
            
            # 清理數據
            data = data.dropna()
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors='coerce')
            data = data.dropna()
            
            if data.empty:
                print(f"  - {stock_id} 清理後無有效數據")
                continue
            
            # 取最近90天數據
            data_90d = data.tail(90)
            
            # 轉換為JSON格式，處理NaN值
            stock_data = {
                'dates': data_90d.index.strftime('%Y-%m-%d').tolist(),
                'open': data_90d['Open'].fillna(0).round(2).tolist(),
                'high': data_90d['High'].fillna(0).round(2).tolist(),
                'low': data_90d['Low'].fillna(0).round(2).tolist(),
                'close': data_90d['Close'].fillna(0).round(2).tolist(),
                'volume': data_90d['Volume'].fillna(0).astype(int).tolist()
            }
            
            # 計算技術指標
            close_prices = data['Close']
            
            # MACD
            exp12 = close_prices.ewm(span=12, adjust=False).mean()
            exp26 = close_prices.ewm(span=26, adjust=False).mean()
            macd = exp12 - exp26
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal
            
            # RSI
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # 取最近90天的指標數據，處理NaN值
            indicators_90d = {
                'dates': data.tail(90).index.strftime('%Y-%m-%d').tolist(),
                'macd': macd.tail(90).fillna(0).round(4).tolist(),
                'signal': signal.tail(90).fillna(0).round(4).tolist(),
                'histogram': histogram.tail(90).fillna(0).round(4).tolist(),
                'rsi': rsi.tail(90).fillna(50).round(2).tolist()  # RSI預設值為50
            }
            
            stock_price_data[stock_id] = {
                'name': momentum_data['dates'][list(momentum_data['dates'].keys())[0]].get(stock_id, {}).get('stock_name', f'股票{stock_id}'),
                'price_data': stock_data,
                'indicators': indicators_90d
            }
            
            print(f"  ✓ 成功處理 {stock_id}")
            
        except Exception as e:
            print(f"  ✗ 處理 {stock_id} 時發生錯誤: {e}")
            continue
    
    # 儲存為JSON文件
    with open('web/stock_price_data.json', 'w', encoding='utf-8') as f:
        json.dump(stock_price_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已生成 {len(stock_price_data)} 隻股票的歷史數據")
    print("📁 數據已保存至: web/stock_price_data.json")

if __name__ == "__main__":
    generate_stock_data()