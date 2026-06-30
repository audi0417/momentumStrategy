# -*- coding: utf-8 -*-
"""Archive daily stock data into historical_data.json + stock_metadata.json."""
from __future__ import annotations

import json
import math
import os

import utils


def archive_stock_data() -> None:
    """Read stocks_data.json, merge into historical_data.json, save metadata."""
    daily_path = "stocks_data.json"
    hist_path = "historical_data.json"
    meta_path = "stock_metadata.json"

    # -- Archive daily → historical --
    if not os.path.exists(daily_path):
        utils.logger.warning("%s 不存在，略過歸檔", daily_path)
        return

    with open(daily_path, encoding="utf-8") as f:
        daily = json.load(f)

    historical: dict = {"dates": {}}
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            historical = json.load(f)

    signal_date = daily.get("last_update")
    if not signal_date:
        utils.logger.error("stocks_data.json 缺少 last_update")
        return

    if signal_date not in historical["dates"]:
        historical["dates"][signal_date] = {}

    for sid, info in daily.get("stocks", {}).items():
        mv = info["momentum"]
        if isinstance(mv, float) and math.isnan(mv):
            mv = None
        historical["dates"][signal_date][sid] = {
            "stock_name": info["stock_name"],
            "momentum": mv,
            "days": info["days"],
            "signals": info.get("signals", []),
        }

    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(historical, f, ensure_ascii=False, indent=2)
    utils.logger.info("歸檔完成 → %s (%s)", hist_path, signal_date)

    # -- metadata --
    all_stocks = utils.get_all_stocks()
    if not all_stocks.empty:
        meta = {row["股票代號"]: row["市場別"] for _, row in all_stocks.iterrows()}
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        utils.logger.info("元資料已儲存 → %s (%s 支)", meta_path, len(meta))


if __name__ == "__main__":
    archive_stock_data()
