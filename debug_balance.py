
from kis_api import KISClient
from main import load_portfolio_config, select_portfolio_file
import argparse

def main():
    # Load config (assuming portfolio.yaml exists or passed)
    # We'll just hardcode looking for portfolio.yaml for simplicity in debug
    import os
    config_file = "portfolio.yaml"
    if not os.path.exists(config_file):
        print("portfolio.yaml not found")
        return

    credentials = load_portfolio_config(config_file)
    client = KISClient(credentials)
    client.get_access_token()
    
    print("Fetching Balance...")
    res = client.get_balance()
    output2 = res.get('output2', [])
    if output2:
        print("\n[Output2 Keys & Values]")
        summary = output2[0]
        for k, v in summary.items():
            print(f"{k}: {v}")
    else:
        print("No output2 found")

if __name__ == "__main__":
    main()
