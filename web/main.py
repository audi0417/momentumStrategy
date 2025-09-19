import os
import json
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta

app = FastAPI()

# Allow all origins for simplicity, you might want to restrict this in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

METADATA = {}
if os.path.exists('../stock_metadata.json'):
    with open('../stock_metadata.json', 'r', encoding='utf-8') as f:
        METADATA = json.load(f)

@app.get("/api/data")
def get_data():
    try:
        with open("../historical_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        return {"error": "historical_data.json not found"}

@app.get("/api/kline/{stock_id}")
def get_kline_chart(stock_id: str):
    try:
        market_type = METADATA.get(stock_id)
        if market_type == '上櫃':
            ticker_symbol = f"{stock_id}.TWO"
        else:
            ticker_symbol = f"{stock_id}.TW"

        # Fetch 90-day data from yfinance
        end_date = datetime.now()
        start_date = end_date - timedelta(days=120)  # Get more days to ensure 90 trading days
        data = yf.download(ticker_symbol, start=start_date, end=end_date)

        if data.empty:
            return JSONResponse(content={"error": "No data found for stock"}, status_code=404)

        # Handle multi-level columns first
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns.values]

        # Clean data - remove rows with NaN values and ensure numeric types
        data = data.dropna()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        data = data.dropna()  # Remove any rows that couldn't be converted

        if data.empty:
            return JSONResponse(content={"error": "No valid data after cleaning"}, status_code=404)

        # Get last 90 trading days
        data_90d = data.tail(90)

        # Ensure we have the required columns
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_cols = [col for col in required_cols if col not in data_90d.columns]
        if missing_cols:
            return JSONResponse(content={"error": f"Missing columns: {missing_cols}"}, status_code=500)

        # Create interactive Plotly candlestick chart
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True,
            vertical_spacing=0.03, 
            row_width=[0.2, 0.7]
        )

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=data_90d.index,
                open=data_90d['Open'],
                high=data_90d['High'],
                low=data_90d['Low'],
                close=data_90d['Close'],
                name='K線',
                increasing_line_color='#ff6b6b',
                decreasing_line_color='#4ecdc4'
            ),
            row=1, col=1
        )

        # Add volume chart
        colors = ['#ff6b6b' if close >= open else '#4ecdc4' 
                 for close, open in zip(data_90d['Close'], data_90d['Open'])]
        
        fig.add_trace(
            go.Bar(
                x=data_90d.index,
                y=data_90d['Volume'],
                name='成交量',
                marker_color=colors,
                opacity=0.7
            ),
            row=2, col=1
        )

        # Update layout
        fig.update_layout(
            title=f'{stock_id} K線圖',
            xaxis_rangeslider_visible=False,
            showlegend=False,
            template='plotly_dark',
            font=dict(size=12),
            margin=dict(l=50, r=50, t=50, b=50)
        )

        # Update y-axes
        fig.update_yaxes(title_text="價格 (TWD)", row=1, col=1)
        fig.update_yaxes(title_text="成交量", row=2, col=1)

        # Convert to JSON using Plotly's built-in method
        import plotly.utils
        chart_json = plotly.utils.PlotlyJSONEncoder().encode({
            "data": fig.data,
            "layout": fig.layout,
            "config": {"responsive": True}
        })
        
        import json
        chart_data = json.loads(chart_json)
        return JSONResponse(content=chart_data)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/indicators/{stock_id}")
def get_indicators_chart(stock_id: str):
    try:
        market_type = METADATA.get(stock_id)
        if market_type == '上櫃':
            ticker_symbol = f"{stock_id}.TWO"
        else:
            ticker_symbol = f"{stock_id}.TW"

        # Fetch data from yfinance
        end_date = datetime.now()
        start_date = end_date - timedelta(days=150)  # Get more data for indicators calculation
        data = yf.download(ticker_symbol, start=start_date, end=end_date)

        if data.empty:
            return JSONResponse(content={"error": "No data found for stock"}, status_code=404)

        # Handle multi-level columns first
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns.values]

        # Clean data - remove rows with NaN values and ensure numeric types
        data = data.dropna()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        data = data.dropna()  # Remove any rows that couldn't be converted

        if data.empty:
            return JSONResponse(content={"error": "No valid data after cleaning"}, status_code=404)
        
        # Ensure we have Close column
        if 'Close' not in data.columns:
            return JSONResponse(content={"error": "Close price data not available"}, status_code=500)

        # Calculate MACD
        exp12 = data['Close'].ewm(span=12, adjust=False).mean()
        exp26 = data['Close'].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        # Calculate RSI
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # Create interactive Plotly indicators chart
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.5]
        )

        # MACD Chart
        fig.add_trace(
            go.Scatter(
                x=data.index, y=macd, 
                mode='lines', name='MACD',
                line=dict(color='#ff6b6b', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=data.index, y=signal,
                mode='lines', name='Signal',
                line=dict(color='#4ecdc4', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Bar(
                x=data.index, y=histogram,
                name='Histogram',
                marker_color='gray',
                opacity=0.5
            ),
            row=1, col=1
        )

        # Add zero line for MACD
        fig.add_hline(y=0, row=1, col=1, line_dash="dash", 
                     line_color="white", opacity=0.5)

        # RSI Chart
        fig.add_trace(
            go.Scatter(
                x=data.index, y=rsi,
                mode='lines', name='RSI',
                line=dict(color='#ffa726', width=2)
            ),
            row=2, col=1
        )

        # Add RSI reference lines
        fig.add_hline(y=70, row=2, col=1, line_dash="dash", 
                     line_color="red", opacity=0.7, 
                     annotation_text="超買 (70)")
        fig.add_hline(y=30, row=2, col=1, line_dash="dash", 
                     line_color="green", opacity=0.7,
                     annotation_text="超賣 (30)")
        fig.add_hline(y=50, row=2, col=1, line_dash="solid", 
                     line_color="white", opacity=0.3)

        # Update layout
        fig.update_layout(
            showlegend=True,
            template='plotly_dark',
            font=dict(size=12),
            margin=dict(l=50, r=50, t=20, b=50)
        )

        # Update y-axes
        fig.update_yaxes(title_text="MACD", row=1, col=1)
        fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])

        # Convert to JSON using Plotly's built-in method
        import plotly.utils
        chart_json = plotly.utils.PlotlyJSONEncoder().encode({
            "data": fig.data,
            "layout": fig.layout,
            "config": {"responsive": True}
        })
        
        import json
        chart_data = json.loads(chart_json)
        return JSONResponse(content=chart_data)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/health")
def health_check():
    return JSONResponse(content={"status": "ok"})

@app.get("/")
def read_root():
    return FileResponse('index.html')

@app.get("/{filepath:path}")
def get_static(filepath: str):
    # Basic security check to prevent directory traversal
    if ".." in filepath:
        return JSONResponse(content={"error": "Not Found"}, status_code=404)
    
    if os.path.exists(filepath):
        return FileResponse(filepath)
    return JSONResponse(content={"error": "Not Found"}, status_code=404)
