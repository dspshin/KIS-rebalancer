
from kis_api import KISClient
from main import load_portfolio_config
import json
import requests

def debug_orderable_cash():
    config_file = "portfolio.yaml"
    credentials = load_portfolio_config(config_file)
    client = KISClient(credentials)
    client.get_access_token()
    
    # TTTC8908R : Inquire Buyable Amount (Available Cash)
    path = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
    url = f"{client.base_url}{path}"
    
    is_virtual = "openapivts" in client.base_url
    # tr_id = "VTTC8908R" if is_virtual else "TTTC8908R" 
    # Actually checking docs, sometimes it's just TTTC8908R for both? 
    # Usually standard rule applies.
    tr_id = "VTTC8908R" if is_virtual else "TTTC8908R"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {client.access_token}",
        "appkey": client.app_key,
        "appsecret": client.app_secret,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": client.cano,
        "ACNT_PRDT_CD": client.acnt_prdt_cd,
        "PDNO": "005930", # Dummy Samsung Elec code is often required to check 'buyable' for a specific stock, but we want generally.
        "ORD_UNPR": "0",
        "ORD_DVSN": "02", # 02: Market, 00: Limit
        "CMA_EVLU_AMT_ICLD_YN": "Y",
        "OVRS_ICLD_YN": "Y"
    }
    
    print(f"Requesting {tr_id}...")
    try:
        res = requests.get(url, headers=headers, params=params)
        print(f"Status: {res.status_code}")
        data = res.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_orderable_cash()
