# -*- coding: utf-8 -*-
"""Generate stock price & indicator data for web frontend."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

import utils


def generate_stock_data() -> None:
    """讀取 historical_data.json → 下載股價 & 計算 MACD/RSI → web/stock_price_data.json"""
    hist_path = "historical_data.json"
    meta_path = "stock_metadata.json"
    out_path = "web/stock_price_data.json"

    if not os.path.exists(hist_path):
        utils.logger.warning("%s 不存在，略過", hist_path)
        return

    with open(hist_path, encoding="utf-8") as f:
        momentum_data = json.load(f)

    metadata: dict[str, str] = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)

    # 所有曾出現的股票
    all_stocks: set[str] = set()
    for date_data in momentum_data["dates"].values():
        all_stocks.update(date_data.keys())
    utils.logger.info("共 %s 支股票待處理", len(all_stocks))

    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)
    out: dict = {}
    stock_list = sorted(all_stocks)
    total = len(stock_list)

    for i, sid in enumerate(stock_list, 1):
        utils.logger.info("[%s/%s] %s", i, total, sid)
        try:
            market = metadata.get(sid, "上市")
            suffix = ".TWO" if market == "上櫃" else ".TW"
            data = yf.download(f"{sid}{suffix}", start=start_date, end=end_date, progress=False)
            if data is None or data.empty:
                utils.logger.warning("  %s 無數據", sid)
                continue

            # 處理多層索引
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [c[0] for c in data.columns]

            data.dropna(inplace=True)
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors="coerce")
            data.dropna(inplace=True)
            if data.empty:
                continue

            d90 = data.tail(90)
            stock_entry = {
                "dates": d90.index.strftime("%Y-%m-%d").tolist(),
                "open": d90["Open"].fillna(0).round(2).tolist(),
                "high": d90["High"].fillna(0).round(2).tolist(),
                "low": d90["Low"].fillna(0).round(2).tolist(),
                "close": d90["Close"].fillna(0).round(2).tolist(),
                "volume": d90["Volume"].fillna(0).astype(int).tolist(),
            }

            # 技術指標
            cp = data["Close"]
            exp12 = cp.ewm(span=12, adjust=False).mean()
            exp26 = cp.ewm(span=26, adjust=False).mean()
            macd = exp12 - exp26
            sig = macd.ewm(span=9, adjust=False).mean()

            delta = cp.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            ind90 = {
                "dates": data.tail(90).index.strftime("%Y-%m-%d").tolist(),
                "macd": macd.tail(90).fillna(0).round(4).tolist(),
                "signal": sig.tail(90).fillna(0).round(4).tolist(),
                "histogram": (macd - sig).tail(90).fillna(0).round(4).tolist(),
                "rsi": rsi.tail(90).fillna(50).round(2).tolist(),
            }

            name = list(momentum_data["dates"].values())[0].get(sid, {}).get("stock_name", f"股票{sid}")
            out[sid] = {"name": name, "price_data": stock_entry, "indicators": ind90}
            utils.logger.info("  ✓ %s (%s)", sid, name)
        except Exception as exc:
            utils.logger.warning("  ✗ %s: %s", sid, exc)

    os.makedirs("web", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    utils.logger.info("✅ 已輸出 %s 支股票 → %s", len(out), out_path)


if __name__ == "__main__":
    generate_stock_data()
