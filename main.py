import requests
import json
import yaml
import os
from kis_api import KISClient
from tabulate import tabulate

def load_portfolio(filepath="portfolio.yaml"):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return []
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
    return data.get('portfolio', [])

def main():
    print("Initializing KIS Rebalancer...")
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
                cur_price = current['cur_price']
                
                diff = target_amt - current_amt
                action = "HOLD"
                qty_diff = 0
                
                if diff > 0:
                    action = "BUY"
                elif diff < 0:
                    action = "SELL"
                
                # Estimate Qty to Buy/Sell (if price is known)
                # If we don't hold it, we need to fetch price, but for now we might handle only existing or assume user inputs price?
                # Actually if we don't hold it, current_holdings won't have price.
                # Ideally we should fetch current price for new items, but let's skip unknown price for now or assume user adds it.
                # For this step, if price is 0 (not held), we can't calculate Qty.
                
                if cur_price > 0:
                    qty_diff = int(abs(diff) / cur_price)
                else:
                    qty_diff = "?"

                plan_data.append([
                    code,
                    name,
                    f"{target_portion*100:.1f}%",
                    f"{target_amt:,.0f}",
                    f"{current_amt:,.0f}",
                    f"{diff:,.0f}",
                    action,
                    f"{qty_diff} qty" if qty_diff != "?" else "Price Unknown"
                ])
                
            headers = ["Code", "Name", "Target %", "Target Amt", "Current Amt", "Diff", "Action", "Est. Qty"]
            print(tabulate(plan_data, headers=headers, tablefmt="pretty"))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
