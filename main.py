import requests
import json
import yaml
import os
import glob
import sys
import time
from dotenv import load_dotenv, dotenv_values
from kis_api import KISClient
from tabulate import tabulate

import argparse
import unicodedata

def get_display_width(s):
    """
    Calculate the display width of a string (East Asian Width).
    Wide/Full-width/Wide-Alpha count as 2, others as 1.
    """
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

def truncate_name(name, max_width=20):
    """
    Truncate string to max_width (visual width).
    """
    current_width = 0
    result = ""
    for char in name:
        char_width = 2 if unicodedata.east_asian_width(char) in ('F', 'W', 'A') else 1
        if current_width + char_width > max_width:
            return result + ".."
        result += char
        current_width += char_width
    return result

def load_portfolio(filepath="portfolio.yaml"):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return []
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
    return data.get('portfolio', [])

def select_portfolio_file(args):
    """
    Select portfolio file based on args or interactive prompt.
    """
    if args.portfolio:
        if os.path.exists(args.portfolio):
            return args.portfolio
        else:
            raise ValueError(f"Portfolio file not found: {args.portfolio}")
    
    # Scan for portfolio*.yaml
    files = sorted(glob.glob("portfolio*.yaml"))
    
    if not files:
        # Fallback to default if no file matches pattern but portfolio.yaml exists (covered by glob usually)
        if os.path.exists("portfolio.yaml"):
            return "portfolio.yaml"
        raise ValueError("No portfolio*.yaml files found.")
        
    if len(files) == 1:
        return files[0]
        
    # Interactive Selection
    print("\n[Select Portfolio]")
    for idx, f in enumerate(files):
        print(f"{idx + 1}. {f}")
        
    while True:
        try:
            choice = input(f"Enter number (1-{len(files)}): ")
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx]
            else:
                print("Invalid number.")
        except ValueError:
            print("Invalid input.")

def load_portfolio_config(filepath):
    """
    Load 'config' section from portfolio yaml and merge with .env
    """
    if not os.path.exists(filepath):
        return None
        
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
        
    config = data.get('config', {})
    if not config:
        return None
        
    # Base credentials from current environment (already loaded by load_dotenv in config.py or main)
    # Actually KISClient loads Config from env.
    # We want to Construct a merged dictionary.
    
    # 1. Start with global env
    final_creds = {
        "APP_KEY": os.getenv("APP_KEY"),
        "APP_SECRET": os.getenv("APP_SECRET"),
        "CANO": os.getenv("CANO"),
        "ACNT_PRDT_CD": os.getenv("ACNT_PRDT_CD"),
        "URL_BASE": os.getenv("URL_BASE", "https://openapi.koreainvestment.com:9443")
    }
    
    # 2. If config has 'env_file', load it
    env_file = config.get('env_file')
    if env_file and os.path.exists(env_file):
        print(f"Loading env from {env_file}...")
        env_vars = dotenv_values(env_file)
        final_creds.update(env_vars)
        
    # 3. Direct Overrides from yaml
    if 'cano' in config:
        final_creds['CANO'] = str(config['cano'])
    if 'acnt_prdt_cd' in config:
        final_creds['ACNT_PRDT_CD'] = str(config['acnt_prdt_cd'])
    if 'app_key' in config: # Allow key override too
        final_creds['APP_KEY'] = str(config['app_key'])
    if 'app_secret' in config:    
        final_creds['APP_SECRET'] = str(config['app_secret'])
        
    return final_creds

# --- NEW: Core Business Logic Functions ---

def fetch_current_status(client):
    """
    Fetches account balance and processes it.
    Returns:
        summary (dict): Account summary (output2)
        holdings (list): List of holding items (output1, filtered > 0)
        total_asset (float)
    """
    print("Fetching Balance...")
    balance_data = client.get_balance()
    output1 = balance_data.get('output1', [])
    output2 = balance_data.get('output2', []) 
    
    summary = {}
    total_asset = 0.0
    
    if output2:
        summary = output2[0]
        total_asset = float(summary.get('tot_evlu_amt', 0))
    
    holdings = []
    if output1:
        for item in output1:
            if int(item['hldg_qty']) > 0:
                holdings.append(item)
                
    return summary, holdings, total_asset

def get_rebalancing_plan(client, portfolio_file, total_asset, holdings):
    """
    Calculates the rebalancing plan.
    Returns a list of plan items (dicts).
    """
    # 1. Map Holdings
    current_holdings = {}
    for item in holdings:
        code = item['pdno']
        current_holdings[code] = {
            'name': item['prdt_name'],
            'qty': int(item['hldg_qty']),
            'cur_price': int(item['prpr']),
            'evlu_amt': float(item['evlu_amt'])
        }
        
    # 2. Load Targets
    targets = load_portfolio(portfolio_file)
    if not targets:
        return []
        
    plan_data = []
    processed_codes = set()
    
    for target in targets:
        code = str(target['code'])
        processed_codes.add(code)
        name = target['name'] # Keep full name
        target_portion = float(target['portion'])
        
        target_amt = total_asset * target_portion
        
        current = current_holdings.get(code, {'evlu_amt': 0, 'cur_price': 0})
        current_amt = current['evlu_amt']
        holdings_cur_price = current['cur_price']
        
        # 3. Market Data
        asking_data = client.get_asking_price(code)
        asking_output = asking_data.get('output1', {})
        asking_output2 = asking_data.get('output2', {}) # Snapshot
        
        bid_price = int(asking_output.get('bidp1', 0))
        ask_price = int(asking_output.get('askp1', 0))
        cur_price = int(asking_output2.get('stck_prpr', 0))
        if cur_price == 0:
             cur_price = int(asking_output.get('stck_prpr', 0))
        if cur_price == 0 and holdings_cur_price > 0:
            cur_price = holdings_cur_price
            
        diff = target_amt - current_amt
        action = "HOLD"
        qty_diff = 0
        est_price = cur_price
        
        if diff > 0:
            action = "BUY"
            if bid_price > 0:
                est_price = bid_price
                qty_diff = int(diff / bid_price)
            elif cur_price > 0:
                est_price = cur_price
                qty_diff = int(diff / cur_price)
                
        elif diff < 0:
            action = "SELL"
            if cur_price > 0:
                est_price = cur_price
                qty_diff = int(abs(diff) / cur_price)
        
        plan_data.append({
            'code': code,
            'name': name,
            'target_portion': target_portion,
            'target_amt': target_amt,
            'current_amt': current_amt,
            'diff': diff,
            'action': action,
            'qty': qty_diff,
            'est_price': est_price,
            'bid_price': bid_price,
            'ask_price': ask_price,
            'asking_output': asking_output,
            'asking_output2': asking_output2
        })
        
    # 4. Handle Surplus Holdings (Not in Portfolio) -> SELL ALL
    for code, holding in current_holdings.items():
        if code in processed_codes:
            continue
            
        name = holding['name']
        current_amt = holding['evlu_amt']
        holding_qty = holding['qty']
        
        # Market Data
        asking_data = client.get_asking_price(code)
        asking_output = asking_data.get('output1', {})
        asking_output2 = asking_data.get('output2', {})
        
        bid_price = int(asking_output.get('bidp1', 0))
        ask_price = int(asking_output.get('askp1', 0))
        cur_price = int(asking_output2.get('stck_prpr', 0))
        if cur_price == 0:
             cur_price = int(asking_output.get('stck_prpr', 0))
             
        est_price = cur_price
        if est_price == 0 and bid_price > 0:
            est_price = bid_price
            
        plan_data.append({
            'code': code,
            'name': name,
            'target_portion': 0.0,
            'target_amt': 0.0,
            'current_amt': current_amt,
            'diff': -current_amt,
            'action': "SELL",
            'qty': holding_qty,
            'est_price': est_price,
            'bid_price': bid_price,
            'ask_price': ask_price,
            'asking_output': asking_output,
            'asking_output2': asking_output2
        })
        
    return plan_data

def execute_plan(client, plan_data, mode, is_buy_enabled, is_sell_enabled):
    """
    Executes the calculated plan.
    """
    print("\n[Execution Started]")
    
    planned_buys = [p for p in plan_data if p['action'] == "BUY" and p['qty'] > 0]
    planned_sells = [p for p in plan_data if p['action'] == "SELL" and p['qty'] > 0]
    
    # 0. Fetch Available Cash Once
    current_cash = 0
    try:
        current_cash = client.get_buyable_cash()
        print(f"Initial Orderable Cash: {current_cash:,} KRW")
    except Exception as e:
        print(f"Warning: Failed to fetch orderable cash ({e}). execution might fail if funds insufficient.")
    
    # 1. Execute SELLS
    if is_sell_enabled and planned_sells:
        print("\n--- Processing SELL Orders ---")
        for order in planned_sells:
            code = order['code']
            name = order['name']
            qty = order['qty']
            ask_price = order['ask_price']
            asking_output = order['asking_output']
            asking_output2 = order['asking_output2']
            
            curr_prc = 0
            try:
                curr_prc = int(asking_output2.get('stck_prpr'))
            except (KeyError, ValueError, TypeError): 
                curr_prc = ask_price

            if mode == 'market':
                 print(f"  [EXEC] [Market-Sell] Selling {name} ({code}) {qty} qty at {curr_prc:,}...")
                 client.place_order(code, qty, curr_prc, "SELL")

            elif mode == 'split':
                 print(f"  [EXEC] [Split-Sell] Selling {name} ({code}) {qty} qty...")
                 q1 = int(qty * 0.33)
                 q2 = int(qty * 0.33)
                 q3 = qty - q1 - q2
                 
                 p1 = ask_price
                 p2 = int(asking_output.get('askp2', 0))
                 p3 = int(asking_output.get('askp3', 0))

                 if q1 > 0 and p1 > 0:
                    print(f"    -> Order 1: {q1} qty at {p1:,}")
                    client.place_order(code, q1, p1, "SELL")
                 if q2 > 0 and p2 > 0:
                    print(f"    -> Order 2: {q2} qty at {p2:,}")
                    client.place_order(code, q2, p2, "SELL")
                 if q3 > 0 and p3 > 0:
                    print(f"    -> Order 3: {q3} qty at {p3:,}")
                    client.place_order(code, q3, p3, "SELL")
                    
    # 2. Execute BUYS
    if is_buy_enabled and planned_buys:
        print("\n--- Processing BUY Orders ---")
        
        # Refetch cash if sells happened
        if is_sell_enabled and planned_sells:
             print("  (Refetching available cash after sells...)")
             try:
                 new_cash = client.get_buyable_cash()
                 print(f"  Updated Orderable Cash: {new_cash:,} KRW")
                 current_cash = new_cash
             except Exception:
                 pass
        
        for order in planned_buys:
            code = order['code']
            name = order['name']
            qty = order['qty']
            bid_price = order['bid_price']
            asking_output = order['asking_output']
            asking_output2 = order['asking_output2']
            
            curr_prc = 0
            try:
                curr_prc = int(asking_output2.get('stck_prpr'))
            except (KeyError, ValueError, TypeError): 
                curr_prc = bid_price

            # Safety Check
            check_price = curr_prc if curr_prc > 0 else bid_price
            if check_price == 0: check_price = 1
            
            max_qty = int(current_cash // check_price)
            
            if qty > max_qty:
                print(f"  [Warning] Local cash check failed (Avail: {current_cash:,}, Needed: ~{qty*check_price:,}). Proceeding to utilize unsettled funds/deposits...")
                
            if qty <= 0:
                print(f"  [Skip] Skipping {name} due to calculated Qty=0.")
                continue
                
            estimated_cost = qty * check_price
            current_cash -= estimated_cost

            if mode == 'market':
                 buy_qty = qty
                 if buy_qty > 0:
                     print(f"  [EXEC] [Market-Buy] Buying {name} ({code}) {buy_qty} qty at Recent Price {curr_prc:,}...")
                     client.place_order(code, buy_qty, curr_prc, "BUY")
            
            elif mode == 'split':
                if qty > 0:
                    print(f"  [EXEC] [Split-Buy] Buying {name} ({code}) {qty} qty...")
                    
                    q1 = int(qty * 0.33)
                    q2 = int(qty * 0.33)
                    q3 = qty - q1 - q2
                    
                    p1 = bid_price
                    p2 = int(asking_output.get('bidp2', 0))
                    p3 = int(asking_output.get('bidp3', 0))
                    
                    if q1 > 0 and p1 > 0:
                        print(f"    -> Order 1: {q1} qty at {p1:,}")
                        client.place_order(code, q1, p1, "BUY")
                    if q2 > 0 and p2 > 0:
                        print(f"    -> Order 2: {q2} qty at {p2:,}")
                        client.place_order(code, q2, p2, "BUY")
                    if q3 > 0 and p3 > 0:
                        print(f"    -> Order 3: {q3} qty at {p3:,}")
                        client.place_order(code, q3, p3, "BUY")

def cancel_open_orders_if_needed(client, is_buy_enabled, is_sell_enabled):
    if is_buy_enabled or is_sell_enabled:
        print("\n[Open Orders Check]")
        try:
            open_orders_data = client.get_open_orders()
            open_orders = open_orders_data.get('output1') or open_orders_data.get('output', [])
            
            if open_orders:
                print(f" -> Found {len(open_orders)} open orders. Cancelling all...")
                for order in open_orders:
                    order_no = order.get('odno')
                    if order_no:
                        print(f"    Cancelling Order {order_no} ({order.get('prdt_name')})...")
                        client.cancel_order(order_no)
                
                print(" -> Waiting 2 seconds for cancellation...")
                time.sleep(2)
            else:
                print(" -> No open orders found.")
        except Exception as e:
            print(f" -> Warning: Failed to check/cancel open orders: {e}")
        print("") 

# --- CLI Main ---

def main():
    parser = argparse.ArgumentParser(description="KIS Rebalancer")
    parser.add_argument("--buy", action="store_true", help="Enable Buy execution")
    parser.add_argument("--sell", action="store_true", help="Enable Sell execution")
    parser.add_argument("--mode", choices=['split', 'market'], default='split', help="Execution mode: split (3-step) or market (100%% current price)")
    parser.add_argument("--portfolio", type=str, help="Path to portfolio yaml file")
    args = parser.parse_args()

    # 1. Select Portfolio File
    try:
        portfolio_file = select_portfolio_file(args)
        print(f"Selected Portfolio: {portfolio_file}")
    except ValueError as e:
        print(f"Error: {e}")
        return

    # 2. Load Portfolio Config
    credentials = load_portfolio_config(portfolio_file)
    if credentials:
        print(f"Loaded Account Config for: {credentials.get('CANO', 'Unknown')}")

    print("Initializing KIS Rebalancer...")
    if args.buy or args.sell:
        print("!!! TRADING MODE ENABLED !!! Orders will be placed.")
        if args.buy: print(f" -> BUY Enabled (Mode: {args.mode})")
        if args.sell: print(f" -> SELL Enabled (Mode: {args.mode})")
    else:
        print("--- Simulation Mode (No Orders) ---")      
        
    try:
        client = KISClient(credentials)
        print("Authenticating...")
        client.get_access_token()
        
        # 3. Clean up Orders
        cancel_open_orders_if_needed(client, args.buy, args.sell)
        
        # 4. Fetch Status
        summary, holdings, total_asset = fetch_current_status(client)
        
        # Print Summary
        if summary:
            print(f"\n[Account Summary] : {client.cano}-{client.acnt_prdt_cd}")
            def get_val(key): return summary.get(key, '0')

            print(f"Total Asset: {float(get_val('tot_evlu_amt')):,.0f} KRW")
            print(f"Deposit: {int(get_val('dnca_tot_amt')):,} KRW")
            print(f"Purchased: {int(get_val('pchs_amt_smtl_amt')):,} KRW")
            print(f"Evaluation: {int(get_val('evlu_amt_smtl_amt')):,} KRW")
            
            try:
                purchase_amt = float(get_val('pchs_amt_smtl_amt'))
                profit_amt = float(get_val('evlu_pfls_smtl_amt'))
                profit_rate = (profit_amt / purchase_amt) * 100 if purchase_amt > 0 else 0.0
            except ValueError:
                profit_rate = 0.0
            print(f"Profit/Loss: {int(float(get_val('evlu_pfls_smtl_amt'))):,} KRW ({profit_rate:.2f}%)")
            
        # Print Holdings
        if holdings:
            print("\n[Holdings]")
            table_data = []
            for item in holdings:
                name = truncate_name(item['prdt_name'])
                evlu_amt = float(item['evlu_amt'])
                portion = (evlu_amt / total_asset) * 100 if total_asset > 0 else 0.0
                
                table_data.append([
                    item['pdno'],
                    name,
                    item['hldg_qty'],
                    f"{float(item['pchs_avg_pric']):,.0f}",
                    f"{int(item['prpr']):,}",
                    item['evlu_pfls_rt'] + "%",
                    f"{portion:.2f}%"
                ])
            headers = ["Code", "Name", "Qty", "Avg Price", "Cur Price", "Return %", "Portion %"]
            print(tabulate(table_data, headers=headers, tablefmt="pretty"))
            
        # 5. Rebalancing Plan
        plan_data = get_rebalancing_plan(client, portfolio_file, total_asset, holdings)
        
        if plan_data:
            print("\n[Rebalancing Plan]")
            table_plan = []
            for item in plan_data:
                display_name = truncate_name(item['name'])
                table_plan.append([
                    item['code'],
                    display_name,
                    f"{item['target_portion']*100:.1f}%",
                    f"{int(item['target_amt']):,}",
                    f"{int(item['current_amt']):,}",
                    f"{int(item['diff']):,}",
                    item['action'],
                    f"{item['qty']:,} qty (@ {item['est_price']:,})" if item['qty'] > 0 else "0"
                ])
            headers = ["Code", "Name", "Target %", "Target Amt", "Current Amt", "Diff", "Action", "Est. Qty (@ Price)"]
            print(tabulate(table_plan, headers=headers, tablefmt="pretty"))

            # 6. Execute IF Enabled
            if args.buy or args.sell:
                execute_plan(client, plan_data, args.mode, args.buy, args.sell)
                
        # 7. Open Orders Check (Final)
        print("\nFetching Open Orders...")
        try:
            open_orders_data = client.get_open_orders()
            open_orders = open_orders_data.get('output1') or open_orders_data.get('output', [])
            
            if not open_orders:
                print("[Open Orders] : None")
            else:
                print(f"[Open Orders] : {len(open_orders)} orders found")
                orders_data = []
                for order in open_orders:
                    rem_qty = order.get('psbl_qty')
                    if not rem_qty or int(rem_qty) == 0:
                        rem_qty = order.get('rmn_qty', 0)
                    tot_qty = order.get('ord_qty', 0)
                    qty_display = f"{int(rem_qty):,} / {int(tot_qty):,}"
                    
                    orders_data.append([
                        order.get('pdno', 'N/A'),
                        order.get('prdt_name', 'N/A'),
                        order.get('sll_buy_dvsn_cd_name', 'Buy/Sell'),
                        qty_display,
                        f"{int(float(order.get('ord_unpr', 0))):,}",
                        order.get('ord_tmd', '')
                    ])
                headers = ["Code", "Name", "Type", "Unexecuted/Total", "Price", "Time"]
                print(tabulate(orders_data, headers=headers, tablefmt="pretty"))
        except Exception as e:
            print(f"[Open Orders] : Failed to fetch ({str(e)})")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
