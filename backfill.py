# -*- coding: utf-8 -*-
"""回填 historical_data.json 中的空白日期。

用途：排程壞掉期間 (成交量查詢失效) 留下的空白交易日，事後以相同的篩選邏輯補算。

與線上流程的對應關係：
  historical_data.json 的 key = 執行日 (run date)
  該筆資料的訊號來源     = 前一個交易日的收盤 (signal date)
所以回填 key=K 時，一律使用 signal = get_previous_trading_day(K) 當天的收盤與成交量。

限制：yfinance 的歷史價格經過除權息回溯調整，重算結果與當時實際執行可能有些微差異。
"""
from __future__ import annotations

import datetime
import json
import sys

import pandas as pd

import utils
from 動能選股 import (  # noqa: E402  — 直接沿用線上的指標與篩選邏輯
    Signal_macd,
    Signal_rsi,
    calculate_momentum,
    parallel_get_stock_data,
)

HIST_PATH = "historical_data.json"
LOOKBACK_DAYS = 180  # 與 get_stock_data 一致


# ---------------------------------------------------------------------------
# 成交量門檻 (批次資料由 utils.build_turnover_map 取得)
# ---------------------------------------------------------------------------
def passes_turnover(sid: str, turnover: dict[str, str]) -> bool:
    try:
        return int(turnover.get(sid, "0").replace(",", "")) >= utils.MIN_TURNOVER
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# 單日重算
# ---------------------------------------------------------------------------
def screen_one_day(
    stock_index: dict[str, pd.DataFrame],
    signal_date: str,
    turnover: dict[str, str],
) -> tuple[dict[str, float], set[str], set[str]]:
    """回傳 (動能股, RSI 股, MACD 股)，切片方式與線上流程一致。"""
    end = pd.Timestamp(signal_date).date()
    start = end - datetime.timedelta(days=LOOKBACK_DAYS)

    momentum: dict[str, float] = {}
    rsi: set[str] = set()
    macd: set[str] = set()

    for sid, df in stock_index.items():
        window = df[(df.index.date > start) & (df.index.date <= end)]
        if len(window) < utils.MIN_DATA_LENGTH:
            continue
        if not passes_turnover(sid, turnover):
            continue

        mv = calculate_momentum(window)
        if mv is not None and mv > utils.MIN_MOMENTUM:
            momentum[sid] = mv

        sig_rsi = Signal_rsi(window, 5, 80)
        if sig_rsi and sig_rsi[-1] == 100:
            rsi.add(sid)

        sig_macd = Signal_macd(window, 12, 26, 9)
        if sig_macd and sig_macd[-1] == 100:
            macd.add(sid)

    return momentum, rsi, macd


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    with open(HIST_PATH, encoding="utf-8") as f:
        historical = json.load(f)
    dates = historical["dates"]

    targets = sorted(k for k in dates if not dates[k])
    if not targets:
        utils.logger.info("沒有空白日期，結束")
        return
    utils.logger.info("待回填 %s 個日期: %s → %s", len(targets), targets[0], targets[-1])

    holidays = utils.get_holiday_schedule()
    signal_of = {k: utils.get_previous_trading_day(k, holidays) for k in targets}

    # -- 連續天數的起點：最後一個有資料的日期 --
    prior = [k for k in sorted(dates) if dates[k] and k < targets[0]]
    state: dict[str, dict] = {}
    if prior:
        seed_date = prior[-1]
        seed_signal = utils.get_previous_trading_day(seed_date, holidays)
        for sid, info in dates[seed_date].items():
            state[sid] = {"days": info.get("days", 1), "last_signal_date": seed_signal}
        utils.logger.info("連續天數承接自 %s (%s 支)", seed_date, len(state))

    # -- 股價：抓一次涵蓋整段 --
    all_stock = utils.get_all_stocks()
    names = dict(zip(all_stock["股票代號"], all_stock["股票名稱"]))
    earliest = signal_of[targets[0]]
    start = (
        datetime.datetime.strptime(earliest, "%Y-%m-%d")
        - datetime.timedelta(days=LOOKBACK_DAYS + 30)
    ).strftime("%Y-%m-%d")
    utils.logger.info("下載股價 %s → 今日 (最早訊號日 %s)…", start, earliest)
    stock_index = parallel_get_stock_data(max_workers=8, start=start)
    if not stock_index:
        utils.logger.error("未取得任何股價資料，中止")
        sys.exit(1)
    utils.logger.info("取得 %s 支股票資料", len(stock_index))

    # -- 逐日重算 --
    for run_date in targets:
        try:
            signal_date, turnover = utils.verify_trading_day(signal_of[run_date], holidays)
        except Exception as exc:
            utils.logger.error("%s 找不到可用的訊號日，跳過: %s", run_date, exc)
            continue
        signal_of[run_date] = signal_date
        utils.logger.info("%s (訊號日 %s) 成交量 %s 檔", run_date, signal_date, len(turnover))

        momentum, rsi, macd = screen_one_day(stock_index, signal_date, turnover)

        entry: dict[str, dict] = {}
        for sid, mv in momentum.items():
            prev = state.get(sid)
            if prev and prev["last_signal_date"] == signal_date:
                days = prev["days"]  # 同一個訊號日 (前一日臨時休市) — 不重複計數
            elif prev and utils.is_consecutive_trading_day(
                prev["last_signal_date"], signal_date, holidays
            ):
                days = prev["days"] + 1
            else:
                days = 1
            state[sid] = {"days": days, "last_signal_date": signal_date}

            signals = []
            if sid in rsi:
                signals.append("rsi")
            if sid in macd:
                signals.append("macd")
            entry[sid] = {
                "stock_name": names.get(sid, f"股票{sid}"),
                "momentum": mv,
                "days": days,
                "signals": signals,
            }

        for sid in list(state):
            if sid not in momentum:
                del state[sid]

        dates[run_date] = entry
        utils.logger.info(
            "  → 動能 %s / RSI %s / MACD %s / 交集 %s",
            len(momentum), len(rsi), len(macd),
            len([s for s in momentum if s in rsi and s in macd]),
        )

    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(historical, f, ensure_ascii=False, indent=2)
    utils.logger.info("已寫回 %s", HIST_PATH)


if __name__ == "__main__":
    main()
