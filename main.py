import requests
import json
import yaml
import os
import glob
import sys
from dotenv import load_dotenv, dotenv_values
from kis_api import KISClient
from tabulate import tabulate

import argparse

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

    # 2. Load Portfolio Config (Account Override)
    credentials = load_portfolio_config(portfolio_file)
    if credentials:
        print(f"Loaded Account Config for: {credentials.get('CANO', 'Unknown')}")



    print("Initializing KIS Rebalancer...")
    if args.buy or args.sell:
        print("!!! TRADING MODE ENABLED !!! Orders will be placed.")
        if args.buy:
            print(f" -> BUY Enabled (Mode: {args.mode})")
        if args.sell:
            print(f" -> SELL Enabled (Mode: {args.mode})")
    else:
        print("--- Simulation Mode (No Orders) ---")      
    try:
        client = KISClient(credentials)
        print("Authenticating...")
        client.get_access_token()
        
        print("Fetching Balance...")
        balance_data = client.get_balance()
        
        # Process and Print
        output1 = balance_data.get('output1', [])
        output2 = balance_data.get('output2', []) # Summary
        
        total_asset = 0.0

        if output2:
            summary = output2[0]
            print(f"\n[Account Summary] : {client.cano}-{client.acnt_prdt_cd}")
            
            # Helper to get value properly formatted or 0
            def get_val(key):
                return summary.get(key, '0')

            total_asset = float(get_val('tot_evlu_amt'))
            print(f"Total Asset: {total_asset:,} KRW")
            print(f"Deposit: {int(get_val('dnca_tot_amt')):,} KRW")
            print(f"Purchased: {int(get_val('pchs_amt_smtl_amt')):,} KRW")
            print(f"Evaluation: {int(get_val('evlu_amt_smtl_amt')):,} KRW")
            
            # Calculate Profit Rate Manually
            try:
                purchase_amt = float(get_val('pchs_amt_smtl_amt'))
                profit_amt = float(get_val('evlu_pfls_smtl_amt'))
                if purchase_amt > 0:
                    profit_rate = (profit_amt / purchase_amt) * 100
                else:
                    profit_rate = 0.0
            except ValueError:
                profit_rate = 0.0
                
            print(f"Profit/Loss: {int(float(get_val('evlu_pfls_smtl_amt'))):,} KRW ({profit_rate:.2f}%)")
            
        current_holdings = {}
        if output1:
            print("\n[Holdings]")
            table_data = []
            
            for item in output1:
                # Filter out empty holdings if necessary
                if int(item['hldg_qty']) > 0:
                    code = item['pdno']
                    name = item['prdt_name']
                    qty = int(item['hldg_qty'])
                    cur_price = int(item['prpr'])
                    evlu_amt = float(item['evlu_amt'])
                    
                    # Store for rebalancing calc
                    current_holdings[code] = {
                        'name': name,
                        'qty': qty,
                        'cur_price': cur_price,
                        'evlu_amt': evlu_amt
                    }

                    portion = (evlu_amt / total_asset) * 100 if total_asset > 0 else 0.0
                    
                    table_data.append([
                        code,
                        name,
                        qty,
                        f"{float(item['pchs_avg_pric']):,.0f}",
                        f"{cur_price:,}",
                        item['evlu_pfls_rt'] + "%",
                        f"{portion:.2f}%"
                    ])
            
            headers = ["Code", "Name", "Qty", "Avg Price", "Cur Price", "Return %", "Portion %"]
            print(tabulate(table_data, headers=headers, tablefmt="pretty"))

        # Rebalancing Logic
        targets = load_portfolio(portfolio_file)
        if targets:
            print("\n[Rebalancing Plan]")
            plan_data = []
            
            # Lists to store execution plans
            planned_buys = []
            planned_sells = []
            
            for target in targets:
                code = str(target['code'])
                name = target['name']
                target_portion = float(target['portion'])
                
                target_amt = total_asset * target_portion
                
                # Check current status
                current = current_holdings.get(code, {'evlu_amt': 0, 'cur_price': 0})
                current_amt = current['evlu_amt']
                # existing cur_price from holdings
                holdings_cur_price = current['cur_price']
                
                # Fetch Real-time Asking Price for accurate calc
                asking_data = client.get_asking_price(code)
                asking_output = asking_data.get('output1', {})
                asking_output2 = asking_data.get('output2', {}) # Snapshot data
                
                # bidp1: Best Bid (Buying Price) - 매수 1호가
                # askp1: Best Ask (Selling Price) - 매도 1호가
                bid_price = int(asking_output.get('bidp1', 0))
                ask_price = int(asking_output.get('askp1', 0))
                
                # Try to get Current Price from output2 (stck_prpr) or output1 or fallback
                cur_price = int(asking_output2.get('stck_prpr', 0))
                if cur_price == 0:
                     cur_price = int(asking_output.get('stck_prpr', 0))

                # Fallback to holdings price if API fails or 0
                if cur_price == 0 and holdings_cur_price > 0:
                    cur_price = holdings_cur_price
                
                diff = target_amt - current_amt
                action = "HOLD"
                qty_diff = 0
                est_price = cur_price # Default for display
                
                if diff > 0:
                    action = "BUY"
                    # User Request: Use Highest Bid Price (매수 1호가) for Buying
                    if bid_price > 0:
                        est_price = bid_price
                        qty_diff = int(diff / bid_price)
                    elif cur_price > 0:
                        est_price = cur_price
                        qty_diff = int(diff / cur_price)
                        
                    if qty_diff > 0:
                        planned_buys.append({
                            'code': code,
                            'name': name,
                            'qty': qty_diff,
                            'price': est_price,
                            'asking_output': asking_output, 
                            'asking_output2': asking_output2,
                            'bid_price': bid_price
                        })
                        
                elif diff < 0:
                    action = "SELL"
                    # For selling, use current price (or could request logic later)
                    if cur_price > 0:
                        est_price = cur_price
                        qty_diff = int(abs(diff) / cur_price)
                    
                    if qty_diff > 0:
                        planned_sells.append({
                            'code': code,
                            'name': name,
                            'qty': qty_diff,
                            'price': est_price,
                            'asking_output': asking_output,
                            'asking_output2': asking_output2,
                            'ask_price': ask_price
                        })

                plan_data.append([
                    code,
                    name,
                    f"{target_portion*100:.1f}%",
                    f"{int(target_amt):,}",
                    f"{int(current_amt):,}",
                    f"{int(diff):,}",
                    action,
                    f"{qty_diff:,} qty (@ {est_price:,})" if qty_diff > 0 else "0"
                ])
                
            headers = ["Code", "Name", "Target %", "Target Amt", "Current Amt", "Diff", "Action", "Est. Qty (@ Price)"]
            print(tabulate(plan_data, headers=headers, tablefmt="pretty"))

            # --- Execution Phase ---
            if args.buy or args.sell:
                print("\n[Execution Started]")
                
                # 0. Fetch Available Cash Once
                current_cash = 0
                try:
                    current_cash = client.get_buyable_cash()
                    print(f"Initial Orderable Cash: {current_cash:,} KRW")
                except Exception as e:
                    print(f"Warning: Failed to fetch orderable cash ({e}). execution might fail if funds insufficient.")
                
                # 1. Execute SELLS first (to free up cash)
                if args.sell and planned_sells:
                    print("\n--- Processing SELL Orders ---")
                    for order in planned_sells:
                        code = order['code']
                        name = order['name']
                        qty = order['qty']
                        # price = order['price']
                        ask_price = order['ask_price']
                        asking_output = order['asking_output']
                        asking_output2 = order['asking_output2']
                        
                        curr_prc = 0
                        try:
                            curr_prc = int(asking_output2.get('stck_prpr'))
                        except (KeyError, ValueError, TypeError): 
                            curr_prc = ask_price # Fallback to Best Ask

                        if args.mode == 'market': # Market Sell 100%
                             print(f"  [EXEC] [Market-Sell] Selling {name} ({code}) {qty} qty at {curr_prc:,}...")
                             client.place_order(code, qty, curr_prc, "SELL")

                        elif args.mode == 'split': # Split Sell (33/33/34 at Ask 1/2/3)
                             print(f"  [EXEC] [Split-Sell] Selling {name} ({code}) {qty} qty...")
                             q1 = int(qty * 0.33)
                             q2 = int(qty * 0.33)
                             q3 = qty - q1 - q2
                             
                             p1 = ask_price # askp1
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
                
                # 2. Execute BUYS (with Clamp Check)
                if args.buy and planned_buys:
                    print("\n--- Processing BUY Orders ---")
                    
                    # NOTE: We do NOT add sold amount to current_cash immediately because settlement takes time (D+2),
                    # unless it's a proxy margin account or the API updates 'ord_psbl_cash' immediately.
                    # For safety, we only use what the API reported + whatever we know is safe.
                    # Actually, for most accounts, you can buy with today's sell proceeds. 
                    # KIS API 'ord_psbl_cash' typically reflects real-time ability including sells.
                    # But since we fetched it BEFORE sells, we might need to refetch or manually add?
                    # **Correct approach**: Refetch cash after sells? 
                    # Or just assume the initial check and whatever was there.
                    # Let's Refetch for maximum safety if sells happened.
                    
                    if args.sell and planned_sells:
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
                        # price = order['price']
                        bid_price = order['bid_price']
                        asking_output = order['asking_output']
                        asking_output2 = order['asking_output2']
                        
                        curr_prc = 0
                        try:
                            curr_prc = int(asking_output2.get('stck_prpr'))
                        except (KeyError, ValueError, TypeError): 
                            curr_prc = bid_price

                        # Check Safety
                        # Calculate estimated total cost for this stock
                        # (using simple price * qty, ignoring split nuances for check)
                        
                        # --- CLAMP LOGIC ---
                        # We calculate the max qty we can afford with current_cash
                        # Max Qty = current_cash // price
                        # If planned qty > Max Qty -> Reduce it.
                        
                        check_price = curr_prc if curr_prc > 0 else bid_price
                        if check_price == 0: check_price = 1 # Avoid div by zero
                        
                        max_qty = int(current_cash // check_price)
                        
                        if qty > max_qty:
                            print(f"  [Limit] Insufficient Cash ({current_cash:,}). Reducing {name} qty from {qty} to {max_qty}...")
                            qty = max_qty
                            
                        if qty <= 0:
                            print(f"  [Skip] Skipping {name} due to insufficient cash (Qty=0).")
                            continue
                            
                        # Deduct estimated cost from local tracking (so next buy doesn't fail)
                        estimated_cost = qty * check_price
                        current_cash -= estimated_cost # Decrement safely
                        # -------------------

                        if args.mode == 'market': # Market Buy
                             buy_qty = qty
                             if buy_qty > 0:
                                 print(f"  [EXEC] [Market-Buy] Buying {name} ({code}) {buy_qty} qty at Recent Price {curr_prc:,}...")
                                 client.place_order(code, buy_qty, curr_prc, "BUY")
                        
                        elif args.mode == 'split': # Split Buy (33/33/34 at Bid 1/2/3)
                            if qty > 0:
                                print(f"  [EXEC] [Split-Buy] Buying {name} ({code}) {qty} qty...")
                                
                                q1 = int(qty * 0.33)
                                q2 = int(qty * 0.33)
                                q3 = qty - q1 - q2
                                
                                p1 = bid_price # bidp1
                                p2 = int(asking_output.get('bidp2', 0))
                                p3 = int(asking_output.get('bidp3', 0))
                                
                                # Sub-order Cash Check?
                                # We already checked total qty vs price. But Split uses different (lower) prices usually, so it's safe.
                                # However, strictly, p1/p2/p3 might be different. 
                                # Since we used 'curr_prc' or 'bid_price' (highest) for check, we are likely safe.
                                
                                if q1 > 0 and p1 > 0:
                                    print(f"    -> Order 1: {q1} qty at {p1:,}")
                                    client.place_order(code, q1, p1, "BUY")
                                if q2 > 0 and p2 > 0:
                                    print(f"    -> Order 2: {q2} qty at {p2:,}")
                                    client.place_order(code, q2, p2, "BUY")
                                if q3 > 0 and p3 > 0:
                                    print(f"    -> Order 3: {q3} qty at {p3:,}")
                                    client.place_order(code, q3, p3, "BUY")

        # Open Orders
        print("\nFetching Open Orders...")
        try:
            open_orders_data = client.get_open_orders()
            # [DEBUG] Check raw response
            # print(f"[DEBUG] Raw Open Orders: {open_orders_data}") 
            
            rt_cd = open_orders_data.get('rt_cd')
            msg_cd = open_orders_data.get('msg_cd')
            
            # Extract list depending on structure
            open_orders = open_orders_data.get('output1') or open_orders_data.get('output', [])
            
            if not open_orders:
                print("[Open Orders] : None (Note: Pension/ISA accounts may not show Reservation Orders via API)")
            else:
                print(f"[Open Orders] : {len(open_orders)} orders found")
                orders_data = []
                for order in open_orders:
                    # Handle multiple APIs:
                    # TTTC8436R (Revocable) -> psbl_qty
                    # TTTC2201R (Daily) -> rmn_qty
                    
                    # Try psbl_qty first, then rmn_qty
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
