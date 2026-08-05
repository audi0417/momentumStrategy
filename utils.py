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
FALLBACK_TRIGGER_RATIO = 0.1  # yfinance 缺漏超過此比例即啟用官方行情備援
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


# ---------------------------------------------------------------------------
# Official OHLC — yfinance 的備援價格來源
# ---------------------------------------------------------------------------
OHLC_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# 還原因子 = 除權息參考價 / 除權息前收盤價。
#
# 不要試圖從每日行情的「漲跌價差」反推：除權息當日 TWSE 的漲跌(+/-) 會標記為
# 'X' (不計算漲跌)、漲跌價差固定 0.00，反推只會拿回當日收盤價本身。實測 2348
# (2026-08-04 除權息) 反推得 0.91129，官方 TWT49U 為 66.09/74.40 = 0.88831。
# 因此上市改讀 TWT49U，上櫃改讀每日行情裡的「次日參考價」。
_EX_RIGHTS_TOL = 0.005


def _to_float(value: Any) -> float | None:
    """行情字串 → float。'--'、'' 等無成交標記回 None。"""
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def fetch_twse_ohlc(date: str) -> dict[str, dict[str, float]]:
    """上市：一次取得全部個股 OHLC + 成交股數 + 當日漲跌 (原始價，未還原)。"""
    fmt_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d")
    payload = robust_get(
        "https://www.twse.com.tw/exchangeReport/MI_INDEX",
        params={"response": "json", "date": fmt_date, "type": "ALLBUT0999"},
    ).json()
    if payload.get("stat") != "OK":
        raise RuntimeError(f"stat={payload.get('stat')}")

    for table in payload.get("tables", []):
        fields = table.get("fields") or []
        if "證券代號" not in fields or "收盤價" not in fields:
            continue
        idx = {name: fields.index(name) for name in (
            "證券代號", "開盤價", "最高價", "最低價", "收盤價",
            "成交股數", "漲跌(+/-)",
        )}
        rows: dict[str, dict[str, float]] = {}
        for row in table["data"]:
            close = _to_float(row[idx["收盤價"]])
            if close is None:
                continue  # 當日無成交
            rows[row[idx["證券代號"]]] = {
                "Open": _to_float(row[idx["開盤價"]]) or close,
                "High": _to_float(row[idx["最高價"]]) or close,
                "Low": _to_float(row[idx["最低價"]]) or close,
                "Close": close,
                "Volume": _to_float(row[idx["成交股數"]]) or 0.0,
                # 'X' = 除權息當日不計算漲跌，用來標記需要向 TWT49U 取還原因子
                "ExRights": "X" in str(row[idx["漲跌(+/-)"]]),
            }
        return rows
    raise RuntimeError("找不到每日收盤行情表格")


def fetch_tpex_ohlc(date: str) -> dict[str, dict[str, float]]:
    """上櫃：同 fetch_twse_ohlc。日期必須用 YYYY/MM/DD，否則 API 靜默回傳最新交易日。"""
    fmt_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%Y/%m/%d")
    payload = robust_get(
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
        params={"response": "json", "date": fmt_date},
    ).json()

    actual, expected = payload.get("date", ""), date.replace("-", "")
    if actual and actual != expected:
        raise RuntimeError(f"回傳日期 {actual} 與預期 {expected} 不符")

    rows: dict[str, dict[str, float]] = {}
    # 欄位序: 0代號 2收盤 3漲跌 4開盤 5最高 6最低 8成交股數
    for row in payload["tables"][0]["data"]:
        close = _to_float(row[2])
        if close is None:
            continue
        rows[row[0]] = {
            "Open": _to_float(row[4]) or close,
            "High": _to_float(row[5]) or close,
            "Low": _to_float(row[6]) or close,
            "Close": close,
            "Volume": _to_float(row[8]) or 0.0,
            # 次日參考價：除權息時 != 收盤價，是上櫃唯一免額外請求的還原依據
            "NextRef": _to_float(row[16]),
        }
    if not rows:
        raise RuntimeError("回傳 0 筆")
    return rows


def fetch_official_ohlc(date: str) -> dict[str, dict[str, float]]:
    """合併上市 + 上櫃當日行情。兩邊皆失敗時拋錯 — 代表該日非交易日或來源全掛。"""
    merged: dict[str, dict[str, float]] = {}
    for market, fetch in (("上市", fetch_twse_ohlc), ("上櫃", fetch_tpex_ohlc)):
        try:
            merged.update(fetch(date))
        except Exception as exc:
            logger.warning("%s %s OHLC 取得失敗: %s", market, date, exc)
    if not merged:
        raise RuntimeError(f"{date} 上市與上櫃行情皆取得失敗")
    return merged


def fetch_twse_ex_rights(start: str, end: str) -> dict[tuple[str, datetime.date], float]:
    """上市除權息還原因子 {(股票代號, 除權息日): 參考價/前收盤價}。

    注意參數名是 startDate — 送 strDate 會拿到「結束日期小於開始日期」的假錯誤。
    """
    payload = robust_get(
        "https://www.twse.com.tw/rwd/zh/exRight/TWT49U",
        params={
            "response": "json",
            "startDate": datetime.datetime.strptime(start, "%Y-%m-%d").strftime("%Y%m%d"),
            "endDate": datetime.datetime.strptime(end, "%Y-%m-%d").strftime("%Y%m%d"),
        },
    ).json()
    if payload.get("stat") != "OK":
        raise RuntimeError(f"stat={payload.get('stat')}")

    factors: dict[tuple[str, datetime.date], float] = {}
    for row in payload.get("data") or []:
        prev_close, ref = _to_float(row[3]), _to_float(row[4])
        if not prev_close or not ref:
            continue
        try:
            # 民國日期 "115年08月04日"
            roc_y, rest = row[0].split("年")
            month, day = rest.replace("日", "").split("月")
            ex_date = datetime.date(int(roc_y) + 1911, int(month), int(day))
        except (ValueError, IndexError):
            continue
        factors[(row[1], ex_date)] = ref / prev_close

    logger.info("上市除權息 %s ~ %s：%s 筆", start, end, len(factors))
    return factors


def _back_adjust(
    bars: list[tuple[datetime.date, dict[str, float]]],
    twse_factors: dict[tuple[str, datetime.date], float],
    stock_id: str,
) -> pd.DataFrame:
    """把原始價序列還原成可比價序列，對齊 yfinance 的 auto_adjust 語意。

    *bars* 需已按日期遞增排序。除權息當日的還原因子回頭套用到所有更早的 K 棒
    (成交量不調整，與 yfinance 一致)。上市取自 TWT49U；上櫃用前一日的次日參考價。
    """
    factors = [1.0] * len(bars)
    for i in range(1, len(bars)):
        day, bar = bars[i]
        prev_bar = bars[i - 1][1]

        if bar.get("ExRights"):  # 上市
            factor = twse_factors.get((stock_id, day))
            if factor is None:
                logger.warning("%s %s 除權息但 TWT49U 無資料，該檔不還原", stock_id, day)
                continue
            factors[i] = factor
        else:  # 上櫃：前一日的次日參考價 != 前一日收盤價 即為除權息
            next_ref, prev_close = prev_bar.get("NextRef"), prev_bar["Close"]
            if next_ref and prev_close and abs(next_ref - prev_close) > _EX_RIGHTS_TOL:
                factors[i] = next_ref / prev_close

    # 由後往前累乘：第 i 根 K 棒要吃掉它「之後」所有除權息的影響
    cumulative = 1.0
    scale = [1.0] * len(bars)
    for i in range(len(bars) - 1, -1, -1):
        scale[i] = cumulative
        cumulative *= factors[i]

    index, records = [], []
    for (day, bar), s in zip(bars, scale):
        index.append(pd.Timestamp(day))
        records.append({
            "Open": bar["Open"] * s,
            "High": bar["High"] * s,
            "Low": bar["Low"] * s,
            "Close": bar["Close"] * s,
            "Volume": bar["Volume"],
        })
    return pd.DataFrame(records, index=pd.DatetimeIndex(index), columns=OHLC_COLUMNS)


def build_official_price_index(
    start: str,
    end: str,
    stock_ids: set[str] | None = None,
    holidays: list[dict[str, str]] | None = None,
) -> dict[str, pd.DataFrame]:
    """以官方每日行情組出 {股票代號: 還原價 DataFrame}，schema 對齊 yfinance。

    *end* 為含括。逐日抓取全市場快照再轉置成個股時間序列 — 官方沒有「一次取
    N 天」的介面，但每日快照是全市場的，所以成本是天數而非股票數。
    抓不到資料的日期直接跳過，因此結果只會包含官方確認過的交易日，
    不會出現 yfinance 那種臨時休市日的假 K 棒。
    """
    if holidays is None:
        holidays = get_holiday_schedule()

    start_d = datetime.datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.datetime.strptime(end, "%Y-%m-%d").date()

    per_stock: dict[str, list[tuple[datetime.date, dict[str, float]]]] = {}
    day, fetched, skipped = start_d, 0, 0
    while day <= end_d:
        if day.weekday() >= 5 or is_holiday(day, holidays):
            day += datetime.timedelta(days=1)
            continue
        try:
            snapshot = fetch_official_ohlc(day.strftime("%Y-%m-%d"))
            fetched += 1
        except Exception:
            logger.info("%s 無官方行情，視為非交易日", day)
            skipped += 1
            day += datetime.timedelta(days=1)
            continue
        for sid, bar in snapshot.items():
            if stock_ids is not None and sid not in stock_ids:
                continue
            per_stock.setdefault(sid, []).append((day, bar))
        day += datetime.timedelta(days=1)

    logger.info(
        "官方行情 %s ~ %s：%s 個交易日 (跳過 %s 日)，%s 檔",
        start, end, fetched, skipped, len(per_stock),
    )
    if not fetched:
        raise RuntimeError(f"{start} ~ {end} 完全取不到官方行情")

    try:
        twse_factors = fetch_twse_ex_rights(start, end)
    except Exception as exc:
        logger.error("上市除權息表取得失敗 (%s)，除權息個股將不還原", exc)
        twse_factors = {}

    return {
        sid: _back_adjust(bars, twse_factors, sid)
        for sid, bars in per_stock.items()
    }


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
