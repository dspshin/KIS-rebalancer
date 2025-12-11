import requests
import json
import yaml
import os
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

def main():
    parser = argparse.ArgumentParser(description="KIS Rebalancer")
    parser.add_argument("--buy", action="store_true", help="Enable Buy execution")
    parser.add_argument("--sell", action="store_true", help="Enable Sell execution")
    parser.add_argument("--mode", choices=['split', 'market'], default='split', help="Execution mode: split (3-step) or market (100%% current price)")
    args = parser.parse_args()



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
        client = KISClient()
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
        targets = load_portfolio()
        if targets:
            print("\n[Rebalancing Plan]")
            plan_data = []
            
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
                        
                elif diff < 0:
                    action = "SELL"
                    # For selling, use current price (or could request logic later)
                    if cur_price > 0:
                        est_price = cur_price
                        qty_diff = int(abs(diff) / cur_price)
                
                # Execution Logic
                # Execution Logic
                # BUY Execution
                if diff > 0 and args.buy:
                     # Get Current Price for Market Buy reference
                    curr_prc = 0
                    try:
                        curr_prc = int(asking_output2.get('stck_prpr'))
                    except (KeyError, ValueError, TypeError): 
                        curr_prc = bid_price 

                    if args.mode == 'market': # Market Price 100%
                         buy_qty = int(diff / curr_prc) if curr_prc > 0 else 0
                         if buy_qty > 0:
                             print(f"  [EXEC] [Market-Buy] Buying {name} ({code}) {buy_qty} qty at Recent Price {curr_prc:,}...")
                             client.place_order(code, buy_qty, curr_prc, "BUY")
                         else:
                             print(f"  [EXEC] [Market-Buy] Failed: Price or Qty is 0")
                    
                    elif args.mode == 'split': # Split Buy (33/33/34 at Bid 1/2/3)
                        if qty_diff > 0:
                            print(f"  [EXEC] [Split-Buy] Buying {name} ({code}) {qty_diff} qty...")
                            
                            q1 = int(qty_diff * 0.33)
                            q2 = int(qty_diff * 0.33)
                            q3 = qty_diff - q1 - q2
                            
                            p1 = bid_price # bidp1
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

                # SELL Execution
                elif diff < 0 and args.sell:
                    curr_prc = 0
                    try:
                        curr_prc = int(asking_output2.get('stck_prpr'))
                    except (KeyError, ValueError, TypeError): 
                        curr_prc = ask_price # Fallback to Best Ask

                    qty_sell = abs(qty_diff)

                    if args.mode == 'market': # Market Sell 100%
                        if qty_sell > 0:
                            print(f"  [EXEC] [Market-Sell] Selling {name} ({code}) {qty_sell} qty at {curr_prc:,}...")
                            client.place_order(code, qty_sell, curr_prc, "SELL")
                    
                    elif args.mode == 'split': # Split Sell (33/33/34 at Ask 1/2/3)
                        if qty_sell > 0:
                             print(f"  [EXEC] [Split-Sell] Selling {name} ({code}) {qty_sell} qty...")
                             q1 = int(qty_sell * 0.33)
                             q2 = int(qty_sell * 0.33)
                             q3 = qty_sell - q1 - q2
                             
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

        # Open Orders
        print("\nFetching Open Orders...")
        try:
            open_orders_data = client.get_open_orders()
            # [DEBUG] Check raw response
            # print(f"[DEBUG] Raw Open Orders: {open_orders_data}") 
            
            rt_cd = open_orders_data.get('rt_cd')
            msg_cd = open_orders_data.get('msg_cd')
            
            if rt_cd != '0':
                if msg_cd == 'OPSQ0002':
                     # Even fallback failed
                    print(f"[Open Orders] : Not Supported/Found (Error {msg_cd})")
                else:
                    print(f"[Open Orders] : Error {msg_cd} - {open_orders_data.get('msg1')}")
            else:
                open_orders = open_orders_data.get('output1') or open_orders_data.get('output', [])
                if open_orders:
                    print("[Open Orders]")
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
                            order['pdno'],
                            order['prdt_name'],
                            order['sll_buy_dvsn_cd_name'],
                            qty_display,
                            f"{int(order['ord_unpr']):,}",
                            order['ord_tmd']
                        ])
                    
                    headers = ["Code", "Name", "Type", "Unexecuted/Total", "Price", "Time"]
                    print(tabulate(orders_data, headers=headers, tablefmt="pretty"))
                else:
                    print("[Open Orders] : None")

        except Exception as e:
            print(f"[Open Orders] : Failed to fetch ({str(e)})")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
