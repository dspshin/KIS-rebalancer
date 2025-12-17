import requests
import json
from config import Config

class KISClient:
    def __init__(self, credentials=None):
        if credentials:
            self.app_key = credentials.get("APP_KEY")
            self.app_secret = credentials.get("APP_SECRET")
            self.cano = credentials.get("CANO")
            self.acnt_prdt_cd = credentials.get("ACNT_PRDT_CD")
            self.base_url = credentials.get("URL_BASE", Config.URL_BASE)
        else:
            Config.validate()
            self.base_url = Config.URL_BASE
            self.app_key = Config.APP_KEY
            self.app_secret = Config.APP_SECRET
            self.cano = Config.CANO
            self.acnt_prdt_cd = Config.ACNT_PRDT_CD
            
        # Token file based on AppKey Hash/Prefix to allow sharing across portfolios with same key
        # but separate for different keys.
        key_prefix = self.app_key[:6] if self.app_key else "unknown"
        self.token_file = f"token_{key_prefix}.json"
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

    def get_access_token(self, force_refresh=False):
        """
        Get OAuth access token.
        Reuse cached token if available.
        """
        if self.access_token and not force_refresh:
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

    def _send_request(self, method, url, headers, params=None, data=None):
        """
        Send API request with automatic token refresh on expiry.
        """
        try:
            if method == 'GET':
                res = requests.get(url, headers=headers, params=params)
            else:
                res = requests.post(url, headers=headers, data=data)
            
            # Check for Token Expiry (500 or 401/403 with specific msg)
            if res.status_code in [500, 401, 403]:
                try:
                    err_data = res.json()
                    msg_cd = err_data.get('msg_cd', '')
                    msg1 = err_data.get('msg1', '')
                    # EGW00123: Expired Token
                    if msg_cd == 'EGW00123' or '만료된 token' in msg1:
                        print(f"[DEBUG] Token Expired ({msg_cd}). Refreshing...")
                        
                        # Refresh Token
                        new_token = self.get_access_token(force_refresh=True)
                        headers['authorization'] = f"Bearer {new_token}"
                        
                        # Retry
                        if method == 'GET':
                            res = requests.get(url, headers=headers, params=params)
                        else:
                            res = requests.post(url, headers=headers, data=data)
                except Exception:
                    # Not JSON or parse error, ignore and let raise_for_status handle it
                    pass
            
            res.raise_for_status()
            return res.json()
        except Exception as e:
            # Re-raise or handle
            raise e

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
        
        return self._send_request('GET', url, headers, params=params)

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
        
        return self._send_request('GET', url, headers, params=params)

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
        
        # res = requests.get(url, headers=headers, params=params)
        # data = res.json()
        try:
             data = self._send_request('GET', url, headers, params=params)
        except Exception as e:
             # If it fails, maybe return simulated empty or just re-raise?
             # existing code didn't try-except standard errors, but relied on manual handling
             print(f"[OpenOrders] Request Failed: {e}")
             return {'rt_cd': '1', 'msg1': str(e)}

        print(f"[DEBUG] Strategy 1 (TTTC8436R) Result: rt_cd={data.get('rt_cd')}, msg_cd={data.get('msg_cd')}, msg1={data.get('msg1')}")
        # print(f"[DEBUG] Full Data: {data}") # Comment in if needed
        
        # Check for Service Code Error (OPSQ0002) - Account Type Mismatch
        if data.get('rt_cd') != '0' and data.get('msg_cd') == 'OPSQ0002':
            print(f"[DEBUG] Attempting Strategy 2 (Pension/ISA API)...")
            # Strategy 2: Pension Account Fallback
            # Path: /uapi/domestic-stock/v1/trading/inquire-daily-ccld (General Daily) or similar? 
            # NO, KIS API Doc: "주식 > 주문/체결 > [국내주식] 주식당일주문체결조회" is TTTC8001R (General).
            # But the user mentioned Pension/ISA. 
            # For Pension/ISA, often the General API works but sometimes fails.
            # Let's try the "Inquire Daily Conclusion" (주식일별주문체결조회) which covers unexecuted.
            
            # Failed with OPSQ0002, trying Strategy 2 (TTTC8001R / VTTC8001R)
            # Reference User's Example: "inquire_daily_ccld"
            # Since we want unexecuted orders, we usually look at recent history (3 months inner).
            # TR_ID for Real: TTTC8001R (pd_dv="inner"), CTSC9215R (pd_dv="before")
            # TR_ID for Demo: VTTC8001R (pd_dv="inner"), VTSC9215R (pd_dv="before")
            
            # We assume "inner" (within 3 months) is sufficient for open orders.
            path2 = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
            url2 = f"{self.base_url}{path2}"
            is_virtual = "openapivts" in self.base_url
            tr_id2 = "VTTC8001R" if is_virtual else "TTTC8001R"
            
            headers2 = headers.copy()
            headers2['tr_id'] = tr_id2
            
            # Prepare params fully populated as per reference
            from datetime import datetime
            today = datetime.now().strftime("%Y%m%d")
            
            params2 = {
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "INQR_STRT_DT": today,      # Start Date
                "INQR_END_DT": today,       # End Date
                "SLL_BUY_DVSN_CD": "00",    # 00:All
                "INQR_DVSN": "00",          # 00:Reverse Order (Recent first)
                "PDNO": "",
                "CCLD_DVSN": "02",          # 02:Unexecuted Only
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",        # 00:All 
                "INQR_DVSN_1": "",          # None:All
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            
            # Note: Pagination logic (tr_cont) is omitted for simplicity in this fallback, 
            # assuming user doesn't have >100 OPEN orders in a single day.
            try:
                # print(f"[DEBUG] Requesting Strategy 2: {url2} with {params2}")
                # res2 = requests.get(url2, headers=headers2, params=params2)
                # data2 = res2.json()
                data2 = self._send_request('GET', url2, headers2, params=params2)
                # If Strategy 2 returns '0' success but empty list, it might be the wrong API for IRP.
                # Or if it fails.
                
                # Check output1 count
                count = 0
                if data2.get('output1'):
                    count = len(data2['output1'])
                
                if count > 0:
                     return data2
                
                # Strategy 3: Specific Pension/IRP API (TTTC2201R)
                print(f"[DEBUG] Strategy 2 returned 0 results. Attempting Strategy 3 (Pension Special API)...")
                
                path3 = "/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld"
                url3 = f"{self.base_url}{path3}"
                tr_id3 = "VTTC2201R" if is_virtual else "TTTC2201R"
                
                headers3 = headers.copy()
                headers3['tr_id'] = tr_id3
                
                # TTTC2201R Params (Pension Daily)
                # Fields: CANO, ACNT_PRDT_CD, INQR_STRT_DT, INQR_END_DT, SLL_BUY_DVSN_CD, INQR_DVSN, PDNO, CCLD_DVSN, etc
                params3 = {
                    "CANO": self.cano,
                    "ACNT_PRDT_CD": self.acnt_prdt_cd,
                    "INQR_STRT_DT": today,
                    "INQR_END_DT": today,
                    "SLL_BUY_DVSN_CD": "00",
                    "INQR_DVSN": "00", 
                    "PDNO": "",
                    # "CCLD_DVSN": "02", # Some docs say this field exists, some say CCLD_NCCS_DVSN
                    "ORD_GNO_BRNO": "",
                    "PCOD": "",
                    "INQR_DVSN_3": "00",
                    "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                    "USER_DVSN_CD": "01", # 01:Personal
                    "CCLD_NCCS_DVSN": "02" # 02: Unexecuted
                }
                
                # res3 = requests.get(url3, headers=headers3, params=params3)
                # data3 = res3.json()
                data3 = self._send_request('GET', url3, headers3, params=params3)
                # print(f"[DEBUG] Strategy 3 Result: {data3.get('rt_cd')}, {data3.get('msg1')}")
                return data3

            except Exception as e:
                print(f"[DEBUG] Strategy 2/3 Failed: {e}")
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
        
        # res = requests.post(url, headers=headers, data=json.dumps(body))
        # res.raise_for_status()
        # data = res.json()
        data = self._send_request('POST', url, headers, data=json.dumps(body))
        
        print(f"    [API OUT] {order_type} Order Result: rt_cd={data.get('rt_cd')}, msg_cd={data.get('msg_cd')}, msg={data.get('msg1')}")
        if data.get('rt_cd') != '0':
            print(f"    [ERROR] Order Failed! Check msg1 above.")
            
            # Check for Retirement Pension Account Error (APBK1744 or similar service errors)
            # msg="퇴직연금계좌는 해당 서비스가 불가합니다."
            if "퇴직연금" in data.get('msg1', '') or data.get('msg_cd') == 'APBK1744':
                print("    [DEBUG] Detected Pension/IRP Account. Retrying with Pension Order API...")
                
                # Pension / New General Order API
                # User suggests TTTC0011U(Sell) / TTTC0012U(Buy).
                # These are newer "General" codes, might work for Pension too or replace 0801U.
                
                path_pension = "/uapi/domestic-stock/v1/trading/order-cash"
                url_pension = f"{self.base_url}{path_pension}"
                
                # Determine TR_ID (New Standard)
                if order_type == "BUY":
                     tr_id_pension = "VTTC0012U" if is_virtual else "TTTC0012U"
                else:
                     tr_id_pension = "VTTC0011U" if is_virtual else "TTTC0011U"
                
                headers_pension = headers.copy()
                headers_pension['tr_id'] = tr_id_pension
                
                # res_p = requests.post(url_pension, headers=headers_pension, data=json.dumps(body))
                try:
                    data_p = self._send_request('POST', url_pension, headers_pension, data=json.dumps(body))
                except Exception as e:
                    print(f"    [DEBUG] Pension API Failed: {e}")
                    data_p = {"rt_cd": "failure", "msg1": f"Pension API Error: {str(e)}"}
                except Exception:
                    print(f"    [DEBUG] Pension API Raw Response: {res_p.status_code} - {res_p.text}")
                    data_p = {"rt_cd": "failure", "msg1": f"Parsing Error (Status: {res_p.status_code})"}
                
                
                print(f"    [API OUT] [Pension] {order_type} Order Result: rt_cd={data_p.get('rt_cd')}, msg={data_p.get('msg1')}")
                return data_p
            
        return data

    def get_buyable_cash(self):
        """
        Fetch orderable cash amount (Available for Buying).
        TR_ID: TTTC8908R (Real) / VTTC8908R (Virtual)
        """
        if not self.access_token:
            self.get_access_token()

        path = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        url = f"{self.base_url}{path}"
        
        is_virtual = "openapivts" in self.base_url
        tr_id = "VTTC8908R" if is_virtual else "TTTC8908R"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        # We need a dummy code to check general buyable amount, but it might vary by stock (margin rate).
        # However, for 100% cash accounts, it should be similar. 
        # Using Samsung Elec (005930) as a safe standard reference.
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": "005930", 
            "ORD_UNPR": "0",
            "ORD_DVSN": "02", # Market
            "CMA_EVLU_AMT_ICLD_YN": "Y",
            "OVRS_ICLD_YN": "Y"
        }
        
        res = self._send_request('GET', url, headers, params=params)
        
        output = res.get('output', {})
        # ord_psbl_cash: 주문가능현금 (증거금률에 따라 미수 포함 가능)
        # nrcwb_buy_amt: 미수없는 매수금액 (순수 현금 100% 주문 가능액)
        nrcwb = int(output.get('nrcwb_buy_amt', 0))
        if nrcwb > 0:
            return nrcwb
            
        # Fallback if nrcwb is 0 (though unlikely for valid response)
        return int(output.get('ord_psbl_cash', 0))

    def cancel_order(self, order_no, total_qty=0):
        """
        Cancel an existing order (Cancel All).
        TR_ID: TTTC0803U (Real) / VTTC0803U (Virtual)
        """
        if not self.access_token:
            self.get_access_token()

        path = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
        url = f"{self.base_url}{path}"
        
        is_virtual = "openapivts" in self.base_url
        tr_id = "VTTC0803U" if is_virtual else "TTTC0803U"

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        # Body for Cancel All
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": "", # API Guide says can be empty or 00950(?). Usually blank works if generated by API.
            "ORGN_ODNO": str(order_no),
            "ORD_DVSN": "00", 
            "RVSE_CNCL_DVSN_CD": "02", # 02: Remnant All Cancel
            "ORD_QTY": "0",  # 0 for All
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y" 
        }
        
        # res = requests.post(url, headers=headers, data=json.dumps(body))
        data = self._send_request('POST', url, headers, data=json.dumps(body))
        
        print(f"    [API OUT] Cancel Order {order_no} Result: rt_cd={data.get('rt_cd')}, msg={data.get('msg1')}")
        return data
