# -*- coding: utf-8 -*-
"""篩選結果健全性檢查 — 供 CI 在流程最後執行。

存在的理由：2026-06-30 至 08-04 期間成交量查詢失效，篩選結果連續 23 個交易日
為 0 支，但 workflow 每天照樣回報 success，因此無人察覺。程式「跑完了」不等於
「跑對了」，這支腳本把「結果為空」變成一個會紅的訊號。

刻意放在 commit/push 之後：即使結果為空也要先歸檔，再讓 workflow 失敗。
"""
from __future__ import annotations

import datetime
import json
import sys

STOCKS_PATH = "stocks_data.json"


def taiwan_date() -> str:
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d")


def main() -> int:
    try:
        with open(STOCKS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ 無法讀取 {STOCKS_PATH}: {exc}")
        return 1

    # 新鮮度：主程式的 main() 會吞掉例外並正常結束，光看 exit code 看不出它中途掛了，
    # 只會留下前一天的舊資料。比對 last_update 才抓得到這種「安靜的失敗」。
    today = taiwan_date()
    last_update = data.get("last_update")
    if last_update != today:
        print(
            f"❌ {STOCKS_PATH} 未更新：last_update={last_update}，今日 (台灣)={today}\n"
            "   主程式可能中途發生例外但被 main() 的 except 吞掉，請檢查上方 log。"
        )
        return 1

    count = len(data.get("stocks", {}))
    if count == 0:
        print(
            f"❌ {data.get('last_update')} 篩選結果為 0 支。\n"
            "   全市場同時無一檔通過門檻極為罕見，優先懷疑資料來源而非行情：\n"
            "   1. 確認 log 中「成交量預載 N 檔」的 N 是否合理 (正常上市+上櫃約 11,000)\n"
            "   2. 確認「篩選統計」的 成交量低 / 無效 是否異常偏高\n"
            "   3. 確認 requirements.txt 鎖定的套件版本是否被改動"
        )
        return 1

    print(f"✅ 篩選結果 {count} 支 ({data.get('last_update')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
