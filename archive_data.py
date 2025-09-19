
import json
import os
import pandas as pd
import requests
import certifi
from datetime import datetime
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def robust_get(url, headers=None, params=None, max_retries=3, timeout=10, delay=2):
    session = requests.Session()
    retries = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.tpex.org.tw/web/stock/aftertrading/daily_quotes/stk_quote_result.php",
        "Origin": "https://www.tpex.org.tw"
    }

    for attempt in range(max_retries):
        try:
            response = session.get(
                url, headers=headers, params=params, timeout=timeout, verify=False
            )
            response.raise_for_status()
            return response

        except (ChunkedEncodingError, ProtocolError) as e:
            print(f"[重試中] 第 {attempt+1} 次 ChunkedEncodingError: {e}")
            time.sleep(delay * (attempt + 1))

        except Exception as e:
            print(f"[錯誤] 第 {attempt+1} 次連線發生例外: {e}")
            time.sleep(delay * (attempt + 1))

    raise Exception(f"在 {max_retries} 次重試後仍無法成功連線: {url}")

def get_all_stocks():
    """Fetches and processes the list of all TWSE and TPEX stocks."""
    try:
        # TWSE listed
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res_twse = robust_get(url_twse)
        twse_listed = pd.read_html(res_twse.text)[0]
        twse_listed.columns = list(twse_listed.iloc[0].values)
        twse_listed = twse_listed.iloc[2:]

        # TPEX listed
        url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        res_tpex = robust_get(url_tpex)
        tpex_listed = pd.read_html(res_tpex.text)[0]
        tpex_listed.columns = list(tpex_listed.iloc[0].values)
        tpex_listed = tpex_listed.iloc[2:]

        all_stock = pd.concat([twse_listed, tpex_listed])
        all_stock.reset_index(drop=True, inplace=True)

        def process_stock_info(text):
            if pd.isna(text): return None, None
            parts = text.strip().split()
            return (parts[0], ' '.join(parts[1:])) if len(parts) >= 2 else (None, None)

        stock_info = all_stock["有價證券代號及名稱"].apply(process_stock_info)
        all_stock.insert(0, "股票代號", stock_info.apply(lambda x: x[0]))
        all_stock.insert(1, "股票名稱", stock_info.apply(lambda x: x[1]))
        all_stock = all_stock.drop(["有價證券代號及名稱"], axis=1)
        all_stock = all_stock[all_stock['CFICode']=="ESVUFR"]
        all_stock = all_stock.dropna(subset=['股票代號', '股票名稱'])
        return all_stock
    except Exception as e:
        print(f"Error fetching stock list: {e}")
        return pd.DataFrame()

def archive_stock_data():
    """
    Reads the daily stock data and archives it into a historical data file.
    Also saves stock metadata (market type).
    """
    daily_data_path = 'stocks_data.json'
    historical_data_path = 'historical_data.json'
    metadata_path = 'stock_metadata.json'

    # --- Archive historical data ---
    if os.path.exists(daily_data_path):
        with open(daily_data_path, 'r', encoding='utf-8') as f:
            daily_data = json.load(f)
        
        if os.path.exists(historical_data_path):
            with open(historical_data_path, 'r', encoding='utf-8') as f:
                historical_data = json.load(f)
        else:
            historical_data = {"dates": {}}

        signal_date = daily_data.get("last_update")
        if signal_date:
            if signal_date not in historical_data["dates"]:
                historical_data["dates"][signal_date] = {}
            for stock_id, stock_info in daily_data.get("stocks", {}).items():
                historical_data["dates"][signal_date][stock_id] = {
                    "stock_name": stock_info["stock_name"],
                    "momentum": stock_info["momentum"],
                    "days": stock_info["days"]
                }
            with open(historical_data_path, 'w', encoding='utf-8') as f:
                json.dump(historical_data, f, ensure_ascii=False, indent=2)
            print(f"Successfully archived data for {signal_date} to '{historical_data_path}'.")
        else:
            print("Error: 'last_update' not found in daily data.")

    # --- Save stock metadata ---
    all_stocks = get_all_stocks()
    if not all_stocks.empty:
        metadata = {row['股票代號']: row['市場別'] for index, row in all_stocks.iterrows()}
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved stock metadata to '{metadata_path}'.")

if __name__ == "__main__":
    archive_stock_data()
