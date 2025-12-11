import requests
import json
from config import Config

class KISClient:
    def __init__(self):
        Config.validate()
        self.base_url = Config.URL_BASE
        self.app_key = Config.APP_KEY
        self.app_secret = Config.APP_SECRET
        self.cano = Config.CANO
        self.acnt_prdt_cd = Config.ACNT_PRDT_CD
        self.token_file = "token.json"
        self.access_token = self._load_token()

    def _load_token(self):
        """Load token from local file if it exists and is valid."""
        import time
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                # Check actual expiry (stored as timestamp)
                # KIS tokens last 24 hours. We'll add a buffer.
                if data.get('expires_at', 0) > time.time() + 60:
                    return data['access_token']
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    def _save_token(self, token, expires_in):
        """Save token to local file."""
        import time
        with open(self.token_file, 'w') as f:
            json.dump({
                'access_token': token,
                'expires_at': time.time() + expires_in
            }, f)

    def get_access_token(self):
        """
        Get OAuth access token.
        Reuse cached token if available.
        """
        if self.access_token:
            return self.access_token

        path = "/oauth2/tokenP"
        url =f"{self.base_url}{path}"
        
        headers = {
            "content-type": "application/json"
        }
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body))
            res.raise_for_status()
            data = res.json()
            self.access_token = data['access_token']
            # Default to 24 hours (86400 seconds) if expires_in is missing or slightly different
            expires_in = int(data.get('expires_in', 86400))
            self._save_token(self.access_token, expires_in)
            return self.access_token
        except Exception as e:
            print(f"Error getting access token: {e}")
            raise

    def get_balance(self):
        """
        Fetch account balance.
        Using domestic stock balance inquiry (TTTC8434R).
        """
        if not self.access_token:
            self.get_access_token()

        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.base_url}{path}"
        
        # TR_ID might differ for Virtual vs Real
        # Real: TTTC8434R
        # Virtual: VTTC8434R
        # We can loosely infer from domain or config. 
        # For safety, let's guess based on URL or just use a config/constant. 
        # But commonly TTTC8434R is for verify (real) and VTTC8434R (virtual).
        # Let's assume Real for now based on typical user request, but handle distinction if possible.
        # Actually, let's make it configurable or robust.
        tr_id = "TTTC8434R"
        if "openapivts" in self.base_url:
            tr_id = "VTTC8434R"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        return res.json()

    def get_asking_price(self, code):
        """
        Fetch asking price (hoga) to get the best bid/ask.
        TR_ID: FHKST01010200 (Real/Virtual same usually, but check)
        """
        if not self.access_token:
            self.get_access_token()

        path = "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        url = f"{self.base_url}{path}"
        
        # This TR_ID is for Quotations, usually same for Real/Virtual or FHKST01010200
        tr_id = "FHKST01010200"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # Stock Market
            "FID_INPUT_ISCD": code
        }
        
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        return res.json()

    def get_open_orders(self):
        """
        Fetch open (unexecuted) orders.
        Attempts Standard `TTTC8436R` first.
        If that fails with Service Code Error (Pension Account), tries `TTTC8430R` or `CTSC9115R` placeholders if known.
        Currently focusing on TTTC8436R (Revocable) -> TTTC8430R (Daily) -> Return Error.
        """
        if not self.access_token:
            self.get_access_token()

        # Strategy 1: Revocable Orders (TTTC8436R) - Best for Unexecuted
        path = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        url = f"{self.base_url}{path}"
        tr_id = "VTTC8436R" if "openapivts" in self.base_url else "TTTC8436R"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0", 
            "INQR_DVSN_2": "0"
        }
        
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        print(f"[DEBUG] Strategy 1 (TTTC8436R) Result: rt_cd={data.get('rt_cd')}, msg_cd={data.get('msg_cd')}, msg1={data.get('msg1')}")
        # print(f"[DEBUG] Full Data: {data}") # Comment in if needed
        
        # Check for Service Code Error (OPSQ0002) - Account Type Mismatch
        if data.get('rt_cd') != '0' and data.get('msg_cd') == 'OPSQ0002':
            # Strategy 2: Pension Account Fallback
            # Strategy 2: Pension Account Fallback
            # Path: /uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld
            # TR_ID: TTTC2201R (KRX) or TTTC2210R (KRX+SOR)
            path2 = "/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld"
            url2 = f"{self.base_url}{path2}"
            tr_id2 = "VTTC2201R" if "openapivts" in self.base_url else "TTTC2201R"
            
            headers2 = headers.copy()
            headers2['tr_id'] = tr_id2
            
            from datetime import datetime, timedelta
            now = datetime.now()
            today = now.strftime("%Y%m%d")
            # Search back 30 days
            start_dt = (now - timedelta(days=30)).strftime("%Y%m%d")
            
            params2 = {
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "INQR_STRT_DT": start_dt,
                "INQR_END_DT": today,
                "SLL_BUY_DVSN_CD": "00", # All
                "INQR_DVSN": "00",       
                "PDNO": "",
                # "CCLD_DVSN": "02",
                "ORD_GNO_BRNO": "",
                "PCOD": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "USER_DVSN_CD": "01",
                "CCLD_NCCS_DVSN": "02"   # 02: Unexecuted Only
            }
            
            try:
                res2 = requests.get(url2, headers=headers2, params=params2)
                data2 = res2.json()
                return data2
            except Exception:
                return data

        return data

    def place_order(self, code, qty, price, order_type="BUY"):
        """
        Place a cash order (Buy/Sell).
        order_type: "BUY" or "SELL"
        """
        if not self.access_token:
            self.get_access_token()

        path = "/uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.base_url}{path}"
        
        # Determine TR_ID
        is_virtual = "openapivts" in self.base_url
        if order_type == "BUY":
            tr_id = "VTTC0802U" if is_virtual else "TTTC0802U"
        else: # SELL
            tr_id = "VTTC0801U" if is_virtual else "TTTC0801U"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": code,
            "ORD_DVSN": "00", # 00: Limit Order (지정가)
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price)
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        res.raise_for_status()
        return res.json()
