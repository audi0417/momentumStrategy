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
_HOLIDAY_CACHE: list[dict[str, str]] | None = None


def get_holiday_schedule() -> list[dict[str, str]]:
    """從 TWSE API 取得假日行事曆 (行程內只取一次)。"""
    global _HOLIDAY_CACHE
    if _HOLIDAY_CACHE is not None:
        return _HOLIDAY_CACHE
    _HOLIDAY_CACHE = _fetch_holiday_schedule()
    return _HOLIDAY_CACHE


def _fetch_holiday_schedule() -> list[dict[str, str]]:
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
    """TWSE + TPEX 上市上櫃普通股清單，isin 失敗時退回 OpenAPI。"""
    try:
        return _get_all_stocks_isin()
    except Exception as exc:
        logger.warning("isin 股票清單失敗 (%s)，改用 OpenAPI 備援", exc)
        return _get_all_stocks_openapi()


def _get_all_stocks_openapi() -> pd.DataFrame:
    """備援：公開發行公司基本資料 (無普通股 CFICode 可濾，改以 4 碼數字代號判斷)。"""
    sources = [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號", "公司簡稱", "上市"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
         "SecuritiesCompanyCode", "CompanyAbbreviation", "上櫃"),
    ]
    records = []
    for url, code_key, name_key, market in sources:
        for row in robust_get(url).json():
            code, name = row.get(code_key), row.get(name_key)
            if code and name and code.isdigit() and len(code) == 4:
                records.append({"股票代號": code, "股票名稱": name.strip(), "市場別": market})
    df = pd.DataFrame(records)
    logger.info("OpenAPI 備援股票清單 %s 支", len(df))
    return df


def _get_all_stocks_isin() -> pd.DataFrame:
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
# Turnover — 每個市場各一次批次查詢，主來源失敗時退回 OpenAPI
#
# 主來源 (MI_INDEX / dailyQuotes) 可指定歷史日期；
# 備援 (OpenAPI) 不吃日期參數、只回傳最新交易日，因此僅在該日就是最新交易日時可用。
# ---------------------------------------------------------------------------
def _to_int(amount: str) -> int:
    """成交金額字串 → int，失敗回 0。"""
    try:
        return int(str(amount).replace(",", ""))
    except (ValueError, TypeError):
        return 0


def fetch_twse_turnover(date: str | None = None) -> dict[str, str]:
    """上市：一次取得全部個股成交金額 {代號: 金額字串}。"""
    if date is None:
        date = get_previous_trading_day()
    fmt_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d")

    try:
        resp = robust_get(
            "https://www.twse.com.tw/exchangeReport/MI_INDEX",
            params={"response": "json", "date": fmt_date, "type": "ALLBUT0999"},
        )
        payload = resp.json()
        if payload.get("stat") != "OK":
            raise RuntimeError(f"stat={payload.get('stat')}")
        for table in payload.get("tables", []):
            fields = table.get("fields") or []
            if "證券代號" in fields and "成交金額" in fields:
                code_i, amount_i = fields.index("證券代號"), fields.index("成交金額")
                rows = {row[code_i]: row[amount_i] for row in table["data"]}
                logger.info("上市成交量 %s：MI_INDEX %s 檔", fmt_date, len(rows))
                return rows
        raise RuntimeError("找不到每日收盤行情表格")
    except Exception as exc:
        logger.warning("上市成交量 MI_INDEX 失敗 (%s)，改用 OpenAPI 備援", exc)

    return _fallback_openapi_turnover(
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        date, code_key="Code", amount_key="TradeValue", market="上市",
    )


def fetch_tpex_turnover(date: str | None = None) -> dict[str, str]:
    """上櫃：一次取得全部個股成交金額 {代號: 金額字串}。"""
    if date is None:
        date = get_previous_trading_day()
    # 必須用 YYYY/MM/DD；送 YYYYMMDD 會被 API 忽略並回傳「最新交易日」
    fmt_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%Y/%m/%d")

    try:
        resp = robust_get(
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
            params={"response": "json", "date": fmt_date},
        )
        payload = resp.json()
        actual = payload.get("date", "")
        expected = date.replace("-", "")
        if actual and actual != expected:
            raise RuntimeError(f"回傳日期 {actual} 與預期 {expected} 不符")
        rows = payload["tables"][0]["data"]
        if not rows:
            raise RuntimeError("回傳 0 筆")
        logger.info("上櫃成交量 %s：dailyQuotes %s 檔", fmt_date, len(rows))
        return {row[0]: row[9] for row in rows}  # row[9] = 成交金額(元)
    except Exception as exc:
        logger.warning("上櫃成交量 dailyQuotes 失敗 (%s)，改用 OpenAPI 備援", exc)

    return _fallback_openapi_turnover(
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
        date, code_key="SecuritiesCompanyCode", amount_key="TransactionAmount",
        market="上櫃",
    )


def _fallback_openapi_turnover(
    url: str, date: str, code_key: str, amount_key: str, market: str
) -> dict[str, str]:
    """OpenAPI 備援：不吃日期參數，只在 *date* 就是最新交易日時採用。"""
    latest = get_previous_trading_day()
    if date != latest:
        logger.error(
            "%s成交量：備援 OpenAPI 只提供最新交易日 (%s)，無法取得 %s",
            market, latest, date,
        )
        return {}
    try:
        rows = robust_get(url).json()
        result = {r[code_key]: r[amount_key] for r in rows if r.get(code_key)}
        logger.info("%s成交量 %s：OpenAPI 備援 %s 檔", market, date, len(result))
        return result
    except Exception as exc:
        logger.error("%s成交量備援亦失敗: %s", market, exc)
        return {}


def build_turnover_map(date: str | None = None) -> dict[str, str]:
    """合併上市 + 上櫃成交金額。兩邊皆空時拋錯 — 這是「篩選結果恆為 0」的病徵。"""
    if date is None:
        date = get_previous_trading_day()
    turnover = fetch_twse_turnover(date)
    turnover.update(fetch_tpex_turnover(date))
    if not turnover:
        raise RuntimeError(f"{date} 上市與上櫃成交量皆取得失敗，篩選結果必然為 0")
    return turnover


def verify_trading_day(
    date: str,
    holidays: list[dict[str, str]] | None = None,
    max_steps: int = 3,
) -> tuple[str, dict[str, str]]:
    """從 *date* 起往前找到第一個有官方成交資料的交易日，回傳 (該日, 成交金額表)。

    TWSE 假日行事曆只涵蓋國定假日，不含臨時休市 (例如颱風假)，而 yfinance 對這類
    日期仍會回傳 K 棒 — 實測 2026-07-10 三個官方來源皆無資料，yfinance 卻有。
    因此改以「官方是否有成交資料」作為交易日的判準。
    """
    if holidays is None:
        holidays = get_holiday_schedule()

    for _ in range(max_steps):
        try:
            return date, build_turnover_map(date)
        except Exception as exc:
            logger.warning("%s 查無官方成交資料 (%s)，往前一個交易日", date, exc)
            date = get_previous_trading_day(date, holidays)

    raise RuntimeError(f"往前找 {max_steps} 個交易日仍取不到成交資料，最後嘗試 {date}")


def resolve_trading_day(
    current_date: str | None = None,
    holidays: list[dict[str, str]] | None = None,
    max_steps: int = 3,
) -> tuple[str, dict[str, str]]:
    """回傳 (經官方成交資料確認過的前一交易日, 該日成交金額表)。"""
    if holidays is None:
        holidays = get_holiday_schedule()
    return verify_trading_day(
        get_previous_trading_day(current_date, holidays), holidays, max_steps
    )

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
