# -*- coding: utf-8 -*-
"""動能選股 — 主程式 (refactored, 2026-06)

Combines momentum / RSI / MACD screening + email notification.
Relies on utils.py for shared config, HTTP, schedule, and logging.
"""
from __future__ import annotations

import datetime
import json
import logging
import math
import os
import random
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TaskProgressColumn

import utils  # 共享模組

console = Console()
logger = logging.getLogger("utils")  # 沿用 utils 的 logger

# ---------------------------------------------------------------------------
# 假日快取 (僅在 main 中取一次)
# ---------------------------------------------------------------------------
_HOLIDAY_SCHEDULE: list[dict[str, str]] | None = None

def _get_holidays() -> list[dict[str, str]]:
    global _HOLIDAY_SCHEDULE
    if _HOLIDAY_SCHEDULE is None:
        _HOLIDAY_SCHEDULE = utils.get_holiday_schedule()
    return _HOLIDAY_SCHEDULE

# ---------------------------------------------------------------------------
# Stock data download  (平行下載)
# ---------------------------------------------------------------------------
def get_stock_data(stock_info: tuple[str, str], max_retries: int = 3) -> tuple[str, pd.DataFrame | None]:
    """下載單一股票歷史資料，回傳 (stock_id, DataFrame | None)。"""
    stock_num, market_type = stock_info
    end_date = utils.get_current_trading_date()
    start = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=180)).strftime("%Y-%m-%d")

    suffix = ".TWO" if market_type in ("上櫃",) else ".TW"
    ticker_str = f"{stock_num}{suffix}"

    for attempt in range(max_retries):
        try:
            time.sleep(0.3 + random.uniform(0, 0.5))
            data = yf.Ticker(ticker_str).history(start=start, end=end_date)
            if not data.empty:
                return stock_num, data
        except Exception:
            pass
        time.sleep(0.5 * (1.5 ** attempt))
    console.print(f"[yellow]⚠ {stock_num} 無法獲取資料 (已重試 {max_retries} 次)[/yellow]")
    return stock_num, None

def parallel_get_stock_data(max_workers: int = 8) -> dict[str, pd.DataFrame]:
    """平行下載所有股票資料。"""
    all_stock = utils.get_all_stocks()
    stock_info_list = [
        (num, all_stock.loc[all_stock["股票代號"] == num, "市場別"].values[0])
        for num in all_stock["股票代號"]
    ]

    stock_index: dict[str, pd.DataFrame] = {}
    total = len(stock_info_list)
    batch_size = 15

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="green"),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]下載股票資料…", total=total)
        for i in range(0, total, batch_size):
            batch = stock_info_list[i : i + batch_size]
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                fut = {pool.submit(get_stock_data, s): s for s in batch}
                for f in as_completed(fut):
                    sid, data = f.result()
                    if data is not None:
                        stock_index[sid] = data
                    progress.update(task, advance=1)
            time.sleep(0.2)
    return stock_index

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
def calculate_momentum(df: pd.DataFrame) -> float | None:
    """5 日動能 = (close[-1] / close[-5] - 1) * 100 (%)。"""
    try:
        close = df["Close"] if "Close" in df.columns else df["close"]
        if len(close) < 5 or close.isnull().any():
            return None
        val = (close.iloc[-1] / close.iloc[-5] - 1) * 100
        return None if math.isnan(val) else val
    except Exception:
        return None

def _rsi_series(data: pd.DataFrame, periods: int) -> pd.Series:
    """回傳 RSI 數列。"""
    df = data.copy()
    change = df["close"].diff()
    gain = change.clip(lower=0)
    loss = (-change).clip(lower=0)
    avg_g = gain.rolling(window=periods).mean()
    avg_l = loss.rolling(window=periods).mean()
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def _macd_series(
    data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    c = data["close"]
    fast_ema = c.ewm(span=fast, adjust=False).mean()
    slow_ema = c.ewm(span=slow, adjust=False).mean()
    macd = fast_ema - slow_ema
    sig = macd.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd, "macdsignal": sig, "macdhist": macd - sig})

def Signal_rsi(df: pd.DataFrame, shortTern: int, longTern: int) -> list[int] | None:
    """RSI 買賣訊號 (100 = 買入)。"""
    try:
        df2 = df.copy()
        df2.columns = df2.columns.str.lower()
        short = _rsi_series(df2, shortTern)
        long_ = _rsi_series(df2, longTern)
        signal = [0]
        for i in range(1, len(long_)):
            b_s, b_l = short.iloc[i - 2], long_.iloc[i - 2]
            l_s, l_l = short.iloc[i - 1], long_.iloc[i - 1]
            t_s, t_l = short.iloc[i], long_.iloc[i]
            if pd.isna(l_s) or pd.isna(l_l):
                signal.append(0)
                continue
            if b_l > b_s and l_l > l_s and t_l > t_s:
                if (b_l - b_s >= l_l - l_s and l_l - l_s > t_l - t_s
                        and l_s < t_s and b_s < l_s):
                    signal.append(100)
                else:
                    signal.append(0)
            elif b_l < b_s and l_l < l_s and t_l < t_s:
                if (b_s - b_l >= l_s - l_l and l_s - l_l > t_s - t_l
                        and l_s > t_s and b_s > l_s):
                    signal.append(-100)
                else:
                    signal.append(0)
            else:
                signal.append(0)
        return signal
    except Exception as exc:
        logger.warning("Signal_rsi error: %s", exc)
        return None

def Signal_macd(
    df: pd.DataFrame, fastperiod: int = 12, slowperiod: int = 26, signalperiod: int = 9
) -> list[int] | None:
    """MACD 買賣訊號 (100 = 買入)。"""
    try:
        df2 = df.copy()
        df2.columns = df2.columns.str.lower()
        macd = _macd_series(df2, fastperiod, slowperiod, signalperiod)
        signal = [0]
        for i in range(1, len(macd)):
            b_m, b_d = macd["macdsignal"].iloc[i - 2], macd["macd"].iloc[i - 2]
            l_m, l_d = macd["macdsignal"].iloc[i - 1], macd["macd"].iloc[i - 1]
            t_m, t_d = macd["macdsignal"].iloc[i], macd["macd"].iloc[i]
            if pd.isna(l_m) or pd.isna(l_d):
                signal.append(0)
                continue
            if b_m > b_d and l_m > l_d and t_m > t_d:
                if (b_m - b_d >= l_m - l_d and l_m - l_d > t_m - t_d
                        and l_d < t_d and b_d < l_d):
                    signal.append(100)
                else:
                    signal.append(0)
            elif b_m < b_d and l_m < l_d and t_m < t_d:
                if (b_d - b_m >= l_d - l_m and l_d - l_m > t_d - t_m
                        and l_d > t_d and b_d > l_d):
                    signal.append(-100)
                else:
                    signal.append(0)
            else:
                signal.append(0)
        return signal
    except Exception as exc:
        logger.warning("Signal_macd error: %s", exc)
        return None

# ---------------------------------------------------------------------------
# 成交量查詢 (惰性快取 + 跨函數共用交易日)
# ---------------------------------------------------------------------------
_TURNOVER_CACHE: dict[str, str] = {}
_TPEX_DATA: list[list[str]] = []
_LAST_TRADING_DAY: str | None = None
_HOLIDAYS: list[dict[str, str]] = []

def set_last_trading_day(day: str | None, holidays: list[dict[str, str]]) -> None:
    global _LAST_TRADING_DAY, _HOLIDAYS
    _LAST_TRADING_DAY = day
    _HOLIDAYS = holidays

def init_turnover_cache() -> None:
    """初始化：預先批次抓取上櫃成交量 (單次 API)。"""
    global _TPEX_DATA
    _TPEX_DATA = utils.fetch_tpex_turnover()
    logger.info("上櫃成交量預載 %s 筆", len(_TPEX_DATA))

def get_turnover(stock_num: str, all_stock_df: pd.DataFrame) -> str:
    """取得單一股票成交金額 (惰性載入 + 快取)。"""
    if stock_num in _TURNOVER_CACHE:
        return _TURNOVER_CACHE[stock_num]

    try:
        market = all_stock_df.loc[all_stock_df["股票代號"] == stock_num, "市場別"].values[0]
    except IndexError:
        _TURNOVER_CACHE[stock_num] = "0"
        return "0"

    # 上櫃：從批次資料查
    if market == "上櫃":
        for row in _TPEX_DATA:
            if row[0] == stock_num:
                val = row[10]
                _TURNOVER_CACHE[stock_num] = val
                return val
        _TURNOVER_CACHE[stock_num] = "0"
        return "0"

    # 上市：直接 API 查 + 快取 (使用預先計算的交易日，避免重複呼叫 holiday API)
    last_day = _LAST_TRADING_DAY or utils.get_current_trading_date()
    fmt_date = datetime.datetime.strptime(last_day, "%Y-%m-%d").strftime("%Y%m%d")
    try:
        resp = requests.get(
            "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
            params={"date": fmt_date, "stockNo": stock_num},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("stat") == "OK" and data.get("data"):
                val = data["data"][-1][2]
                _TURNOVER_CACHE[stock_num] = val
                return val
    except Exception:
        pass
    _TURNOVER_CACHE[stock_num] = "0"
    return "0"

# ---------------------------------------------------------------------------
# 通用篩選器
# ---------------------------------------------------------------------------
def filter_stocks(
    stock_index: dict[str, pd.DataFrame],
    indicator_fn: Any,
    condition_args: dict[str, Any] | None = None,
    min_value: float | None = None,
) -> dict[str, Any]:
    """通用篩選：數據長度檢查 → 指標計算 → 成交量門檻。"""
    result: dict[str, Any] = {}
    skip = {"length": 0, "null": 0, "threshold": 0, "turnover_low": 0, "turnover_err": 0}

    for sid, df in stock_index.items():
        if len(df) < utils.MIN_DATA_LENGTH:
            skip["length"] += 1
            continue

        val = indicator_fn(df, **(condition_args or {})) if condition_args else indicator_fn(df)
        if val is None:
            skip["null"] += 1
            continue

        # 列表型：檢查最後一筆
        if isinstance(val, list):
            if val[-1] != 100:
                skip["threshold"] += 1
                continue
            indicator_val = val[-1]
        else:
            if min_value is not None and val <= min_value:
                skip["threshold"] += 1
                continue
            indicator_val = val

        # 成交量檢查 (惰性查詢 + 自動快取)
        if sid not in _TURNOVER_CACHE:
            get_turnover(sid, all_stock)
        turnover_str = _TURNOVER_CACHE.get(sid, "0")
        try:
            turnover_num = int(turnover_str.replace(",", ""))
        except (ValueError, AttributeError):
            skip["turnover_err"] += 1
            continue

        if turnover_num >= utils.MIN_TURNOVER:
            result[sid] = indicator_val
        else:
            skip["turnover_low"] += 1

    total = sum(skip.values()) + len(result)
    logger.info(
        "篩選統計 (%s 支): 長度不足=%s 無效=%s 未達閾值=%s 成交量低=%s 成交量錯誤=%s 合格=%s",
        total, skip["length"], skip["null"], skip["threshold"],
        skip["turnover_low"], skip["turnover_err"], len(result),
    )
    return result

# ---------------------------------------------------------------------------
# 顯示 / 郵件
# ---------------------------------------------------------------------------
def display_results(
    stocks: dict[str, Any] | list[str],
    title: str,
    include_value: bool = True,
    value_name: str = "值",
    stock_data: dict | None = None,
) -> None:
    """終端輸出篩選結果。"""
    console.print(f"\n{title}:")
    console.print("=" * 50)
    if not stocks:
        console.print(f"[yellow]無符合 {title} 的股票[/yellow]")
        console.print("=" * 50)
        return

    items = sorted(stocks.items(), key=lambda x: x[1], reverse=True) if isinstance(stocks, dict) else [(s, None) for s in stocks]
    console.print(f"[green]共 {len(items)} 支:[/green]")

    for stock, val in items:
        name = all_stock.loc[all_stock["股票代號"] == stock, "股票名稱"].values[0]
        tv = utils.format_number(get_turnover(stock, all_stock))
        days = ""
        if stock_data and stock in stock_data.get("stocks", {}):
            days = f", 連續 {stock_data['stocks'][stock]['days']} 天"
        if include_value and val is not None:
            console.print(f"  {stock} {name} ({value_name}: {val:.2f}%, 成交量: {tv}{days})")
        else:
            console.print(f"  {stock} {name} (成交量: {tv}{days})")
    console.print("=" * 50)

def build_mail_content(
    momentum_stocks: dict,
    rsi_stocks: dict,
    macd_stocks: dict,
    final_stocks: list[str],
    total_stocks: int,
    stock_data: dict,
) -> str:
    """產生郵件純文字內容。"""
    lines = [
        "股票篩選結果",
        "=" * 30,
        "",
        f"篩選總數: {total_stocks} 支股票",
        "",
    ]
    for title, d, is_dict, vname in [
        ("動能選股", momentum_stocks, True, "動能"),
        ("RSI 選股", rsi_stocks, False, None),
        ("MACD 選股", macd_stocks, False, None),
    ]:
        lines.append(f"{title} (共 {len(d)} 支)")
        lines.append("-" * 20)
        if d:
            for s, v in (sorted(d.items(), key=lambda x: x[1], reverse=True) if is_dict else [(s, None) for s in d]):
                name = all_stock.loc[all_stock["股票代號"] == s, "股票名稱"].values[0]
                tv = utils.format_number(get_turnover(s, all_stock))
                d_info = stock_data["stocks"][s]["days"] if s in stock_data.get("stocks", {}) else 1
                if is_dict:
                    lines.append(f"• {s} {name}: {vname} {v:.2f}%, 成交量 {tv}, 連續 {d_info} 天")
                else:
                    lines.append(f"• {s} {name}: 成交量 {tv}")
        lines.append("")

    lines.append("最終篩選結果")
    lines.append("-" * 20)
    if final_stocks:
        lines.append(f"符合所有條件 (共 {len(final_stocks)} 支):")
        for s in final_stocks:
            name = all_stock.loc[all_stock["股票代號"] == s, "股票名稱"].values[0]
            m = momentum_stocks[s]
            tv = utils.format_number(get_turnover(s))
            lines.append(f"• {s} {name}: 動能 {m:.2f}%, 成交量 {tv}")
    else:
        lines.append("本日無股票符合所有條件")
    return "\n".join(lines)

def send_mail(sender: str, password: str, receiver: str, content: str) -> None:
    """透過 Gmail SMTP 發送郵件。"""
    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = receiver
        msg["Subject"] = f"股票篩選結果 - {utils.get_current_trading_date()}"
        msg.attach(MIMEText(content, "plain", "utf-8"))

        svr = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        svr.login(sender, password)
        svr.send_message(msg)
        svr.quit()
        logger.info("郵件發送成功")
    except Exception as exc:
        logger.error("郵件發送失敗: %s", exc)

# ---------------------------------------------------------------------------
# 連續天數更新
# ---------------------------------------------------------------------------
def update_momentum_stocks(
    momentum_stocks: dict[str, float | int],
    rsi_stocks: dict[str, int] | None,
    macd_stocks: dict[str, int] | None,
) -> dict:
    """更新 stocks_data.json 的連續天數與信號。"""
    holidays = _get_holidays()
    current_date = utils.get_current_trading_date()
    signal_date = utils.get_previous_trading_day(current_date, holidays)
    logger.info("信號日期: %s", signal_date)

    data = _load_stock_data()
    current_ids = set(momentum_stocks.keys())
    rsi_set = set(rsi_stocks or {})
    macd_set = set(macd_stocks or {})

    for sid, momentum in momentum_stocks.items():
        name = all_stock.loc[all_stock["股票代號"] == sid, "股票名稱"].values[0]
        signals = []
        if sid in rsi_set:
            signals.append("rsi")
        if sid in macd_set:
            signals.append("macd")

        if sid in data["stocks"]:
            prev = data["stocks"][sid]["last_signal_date"]
            if utils.is_consecutive_trading_day(prev, signal_date, holidays):
                data["stocks"][sid]["days"] += 1
            else:
                data["stocks"][sid]["days"] = 1
            mv = float(momentum)
            data["stocks"][sid]["momentum"] = None if math.isnan(mv) else mv
            data["stocks"][sid]["last_signal_date"] = signal_date
            data["stocks"][sid]["signals"] = signals
        else:
            mv = float(momentum)
            data["stocks"][sid] = {
                "stock_name": name,
                "momentum": None if math.isnan(mv) else mv,
                "days": 1,
                "last_signal_date": signal_date,
                "signals": signals,
            }

    # 移除已無信號的
    for sid in list(data["stocks"]):
        if sid not in current_ids:
            logger.info("移除 %s %s", sid, data["stocks"][sid]["stock_name"])
            del data["stocks"][sid]

    data["last_update"] = current_date
    _save_stock_data(data)
    return data

def _load_stock_data() -> dict:
    fp = "stocks_data.json"
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("JSON 格式錯誤，重新建立")
    return {"last_update": datetime.datetime.now().strftime("%Y-%m-%d"), "stocks": {}}

def _save_stock_data(data: dict) -> None:
    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("stocks_data.json 已儲存")

# ---------------------------------------------------------------------------
# 全域股票清單變數（供 email 等用）
# ---------------------------------------------------------------------------
all_stock: pd.DataFrame = pd.DataFrame()

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    global all_stock
    try:
        # ---- 交易日檢查 -------------------------------------------------
        taiwan_now = utils.get_taiwan_datetime()
        current_date = utils.get_current_trading_date()
        holidays = _get_holidays()

        console.print("[cyan]系統檢查[/cyan]")
        console.print(f"台灣時間: {taiwan_now}")
        console.print(f"當前日期: {current_date}")

        if taiwan_now.weekday() >= 5:
            console.print("[yellow]週末，程式終止[/yellow]")
            return
        if holidays and utils.is_holiday(taiwan_now.date(), holidays):
            console.print("[yellow]國定假日，程式終止[/yellow]")
            return
        console.print("[green]交易日，繼續執行[/green]")
        console.print("=" * 50)

        # ---- 1. 取得股票清單與下載歷史資料 --------------------------------
        logger.info("取得股票清單…")
        all_stock = utils.get_all_stocks()
        logger.info("上市櫃普通股共 %s 支", len(all_stock))

        logger.info("開始下載股價資料 (平行下載, 8 workers)…")
        stock_index = parallel_get_stock_data(max_workers=8)
        if not stock_index:
            console.print("[red]未取得任何股票資料，結束[/red]")
            return
        logger.info("成功取得 %s 支股票資料", len(stock_index))

        # ---- 2. 初始化成交量快取 + 交易日快取 (避免重複呼叫 holiday API) -------
        init_turnover_cache()
        last_trading_day = utils.get_previous_trading_day(holiday_schedule=holidays)
        set_last_trading_day(last_trading_day, holidays)

        # ---- 3. 篩選 ---------------------------------------------------
        logger.info("動能篩選…")
        momentum_stocks = filter_stocks(
            stock_index, calculate_momentum,
            min_value=utils.MIN_MOMENTUM,
        )

        logger.info("RSI 篩選…")
        rsi_stocks = filter_stocks(
            stock_index, Signal_rsi,
            condition_args={"shortTern": 5, "longTern": 80},
        )

        logger.info("MACD 篩選…")
        macd_stocks = filter_stocks(
            stock_index, Signal_macd,
            condition_args={"fastperiod": 12, "slowperiod": 26, "signalperiod": 9},
        )

        # ---- 4. 更新連續天數 --------------------------------------------
        logger.info("更新連續天數…")
        updated_data = update_momentum_stocks(momentum_stocks, rsi_stocks, macd_stocks)

        # ---- 5. 顯示結果 ------------------------------------------------
        display_results(momentum_stocks, "動能篩選", stock_data=updated_data)
        display_results(rsi_stocks, "RSI 篩選", include_value=False, stock_data=updated_data)
        display_results(macd_stocks, "MACD 篩選", include_value=False, stock_data=updated_data)

        final_stocks = [
            s for s in momentum_stocks if s in rsi_stocks and s in macd_stocks
        ]
        console.print("\n[cyan]最終篩選結果[/cyan]")
        console.print("=" * 50)
        if final_stocks:
            console.print(f"[green]符合所有條件: {len(final_stocks)} 支[/green]")
            for s in final_stocks:
                name = all_stock.loc[all_stock["股票代號"] == s, "股票名稱"].values[0]
                console.print(f"  {s} {name}: 動能 {momentum_stocks[s]:.2f}%")
        else:
            console.print("[yellow]無股票符合所有條件[/yellow]")

        # ---- 6. 郵件 ---------------------------------------------------
        sender = os.getenv("SENDER_EMAIL")
        app_pwd = os.getenv("APP_PASSWORD")
        receiver = os.getenv("RECIVER_EMAIL")
        if sender and app_pwd and receiver:
            content = build_mail_content(
                momentum_stocks, rsi_stocks, macd_stocks,
                final_stocks, len(stock_index), updated_data,
            )
            send_mail(sender, app_pwd, receiver, content)
        else:
            logger.warning("郵件環境變數未設定，略過發信")

    except Exception as exc:
        console.print(f"[red]執行錯誤: {exc}[/red]")
        logger.exception("main 例外")
    finally:
        console.print("\n[green]程式執行完成[/green]")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("動能選股系統 開始執行…")
    print("-" * 50)
    try:
        main()
    except KeyboardInterrupt:
        print("\n使用者中斷")
    except Exception as exc:
        print(f"未預期錯誤: {exc}")
