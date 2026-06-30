# -*- coding: utf-8 -*-
"""
Shared utilities for momentumStrategy.

Centralizes: config constants, Taiwan market schedule logic,
robust HTTP session, stock list fetching, turnover cache, logging.
"""
from __future__ import annotations

import datetime
import json
import logging
import math
import os
import random
import time
from io import StringIO
from typing import Any

import certifi
import pandas as pd
import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MIN_DATA_LENGTH = 90          # 最少數據天數
MIN_MOMENTUM = 7              # 動能門檻 (%)
MIN_TURNOVER = 100_000_000    # 最低成交量 1 億
TW_OFFSET = datetime.timedelta(hours=8)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logger(name: str = __name__) -> logging.Logger:
    """Return a logger that writes ISO‑8601‑stamped lines to stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    return logger

logger = setup_logger("utils")

# ---------------------------------------------------------------------------
# Taiwan time helpers
# ---------------------------------------------------------------------------
def get_taiwan_datetime() -> datetime.datetime:
    """當前台灣時間 (UTC+8)."""
    return datetime.datetime.now(datetime.timezone(TW_OFFSET))

def get_current_trading_date() -> str:
    """今日台灣日期 YYYY-MM-DD."""
    return get_taiwan_datetime().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Holiday / trading‑day helpers
# ---------------------------------------------------------------------------
def get_holiday_schedule() -> list[dict[str, str]]:
    """從 TWSE API 取得假日行事曆。"""
    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            logger.info("假日資料獲取成功，共 %s 筆", len(data))
            return data
        logger.warning("假日資料 HTTP %s", resp.status_code)
    except Exception as exc:
        logger.warning("假日資料請求失敗: %s", exc)
    return []

def is_holiday(d: datetime.date, holiday_schedule: list[dict[str, str]]) -> bool:
    """回傳 True 如果 *d* 在 holiday_schedule 裡 (多種日期格式)。"""
    if not holiday_schedule:
        return False
    # 預先計算好所有可能的格式
    fmt_1 = f"1{d.strftime('%y%m%d')}"
    fmt_2 = d.strftime("%Y%m%d")
    fmt_3 = d.strftime("%Y/%m/%d")
    fmt_4 = f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
    for h in holiday_schedule:
        hd = h.get("Date", "")
        if hd in (fmt_1, fmt_2, fmt_3, fmt_4):
            return True
    return False

def get_previous_trading_day(
    current_date: str | None = None,
    holiday_schedule: list[dict[str, str]] | None = None,
) -> str | None:
    """回傳前一個交易日 YYYY-MM-DD (最多往前找 10 天)。"""
    if current_date is None:
        current_date = get_current_trading_date()
    current = datetime.datetime.strptime(current_date, "%Y-%m-%d")
    if holiday_schedule is None:
        holiday_schedule = get_holiday_schedule()

    # 週一往前 3 天，其餘 1 天
    days_to_subtract = 3 if current.weekday() == 0 else 1

    for i in range(days_to_subtract, days_to_subtract + 10):
        prev = current - datetime.timedelta(days=i)
        if prev.weekday() >= 5:
            continue
        if is_holiday(prev, holiday_schedule):
            continue
        return prev.strftime("%Y-%m-%d")

    # fallback ── 保守往前推
    return (current - datetime.timedelta(days=days_to_subtract)).strftime("%Y-%m-%d")

def is_consecutive_trading_day(
    earlier_date: str,
    later_date: str,
    holiday_schedule: list[dict[str, str]],
) -> bool:
    """earlier_date 與 later_date 之間無任何交易日 → 連續。"""
    if earlier_date == later_date:
        return True
    earlier = datetime.datetime.strptime(earlier_date, "%Y-%m-%d").date()
    later = datetime.datetime.strptime(later_date, "%Y-%m-%d").date()
    if later <= earlier:
        return False
    for d in range(1, (later - earlier).days):
        dt = earlier + datetime.timedelta(days=d)
        if dt.weekday() >= 5:
            continue
        if is_holiday(dt, holiday_schedule):
            continue
        return False  # 中間存在交易日 → 不連續
    return True

# ---------------------------------------------------------------------------
# Robust HTTP session
# ---------------------------------------------------------------------------
def robust_get(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    max_retries: int = 3,
    timeout: int = 30,
    delay: float = 2,
    verify: bool = False,
) -> requests.Response:
    """Retry‑capable GET with exponential backoff."""
    session = requests.Session()
    retries = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))

    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.tpex.org.tw/web/stock/aftertrading/daily_quotes/stk_quote_result.php",
        "Origin": "https://www.tpex.org.tw",
    }
    if headers:
        default_headers.update(headers)

    for attempt in range(max_retries):
        try:
            resp = session.get(
                url, headers=default_headers, params=params,
                timeout=timeout, verify=verify,
            )
            resp.raise_for_status()
            return resp
        except (ChunkedEncodingError, ProtocolError) as exc:
            logger.warning("重試 %s/%s — Chunked/Protocol error: %s", attempt + 1, max_retries, exc)
        except requests.RequestException as exc:
            logger.warning("重試 %s/%s — %s", attempt + 1, max_retries, exc)
        time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"在 {max_retries} 次重試後仍無法連線: {url}")

# ---------------------------------------------------------------------------
# Stock list
# ---------------------------------------------------------------------------
def get_all_stocks() -> pd.DataFrame:
    """TWSE + TPEX 上市上櫃普通股清單。"""
    def _fetch(mode: int) -> pd.DataFrame:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        resp = robust_get(url)
        resp.encoding = "MS950"
        df = pd.read_html(StringIO(resp.text))[0]
        df.columns = list(df.iloc[0].values)
        return df.iloc[2:]

    df = pd.concat([_fetch(2), _fetch(4)], ignore_index=True)

    # 解析「有價證券代號及名稱」
    def _split(text: str) -> tuple[str | None, str | None]:
        if pd.isna(text):
            return None, None
        parts = str(text).strip().split(maxsplit=1)
        return (parts[0], parts[1]) if len(parts) >= 2 else (None, None)

    info = df["有價證券代號及名稱"].apply(_split)
    df.insert(0, "股票代號", info.apply(lambda x: x[0]))
    df.insert(1, "股票名稱", info.apply(lambda x: x[1]))
    df.drop(columns=["有價證券代號及名稱"], inplace=True)

    df = df[df["CFICode"] == "ESVUFR"]
    return df.dropna(subset=["股票代號", "股票名稱"])

# ---------------------------------------------------------------------------
# Turnover pre‑fetch (批次快取)
# ---------------------------------------------------------------------------
def pre_fetch_turnovers(
    stock_ids: list[str],
    all_stock: pd.DataFrame,
    tpex_turnover: list[list[str]],
) -> dict[str, str]:
    """批次查詢所有股票的成交金額，回傳 {stock_id: turnover_str}。"""
    cache: dict[str, str] = {}
    current_date = get_current_trading_date()
    last_trading_day = get_previous_trading_day(current_date)

    for sid in stock_ids:
        try:
            market = all_stock.loc[
                all_stock["股票代號"] == sid, "市場別"
            ].values[0]
        except IndexError:
            continue

        if market == "上櫃":
            # 從已取得的上櫃資料查
            for row in tpex_turnover:
                if row[0] == sid:
                    cache[sid] = row[10]
                    break
        else:
            # 上市 ── TWSE STOCK_DAY API
            date_obj = datetime.datetime.strptime(
                last_trading_day, "%Y-%m-%d"
            ).date() if last_trading_day else get_taiwan_datetime().date()
            fmt_date = date_obj.strftime("%Y%m%d")
            try:
                resp = requests.get(
                    "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
                    params={"date": fmt_date, "stockNo": sid},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("stat") == "OK" and data.get("data"):
                        # 取最後一筆的成交金額 (index 2)
                        cache[sid] = data["data"][-1][2]
            except Exception:
                pass
    return cache

# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------
def format_number(number: Any) -> str:
    """格式化成千分位字串，例如 1234567 → "1,234,567"."""
    try:
        if isinstance(number, str):
            number = int(number.replace(",", ""))
        return f"{int(number):,d}"
    except (ValueError, TypeError):
        return str(number)
