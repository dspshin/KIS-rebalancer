import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def fetch_history(codes, years=3):
    """
    Fetches historical data for given codes.
    Returns:
        prices_df: DataFrame of closing prices
        start_date: Actual start date of the backtest (may be adjusted)
        tickers_names: Dictionary of Code -> Name (if passed or fetched?)
                       Actually we just need codes for fdr.
    """
    end_date = datetime.today()
    start_date = end_date - relativedelta(years=years)
    
    # 1. Fetch Data
    df_list = []
    
    print(f"Fetching data from {start_date.strftime('%Y-%m-%d')}...")
    
    valid_codes = []
    
    for code in codes:
        try:
            # KRX stock code
            df = fdr.DataReader(code, start_date, end_date)
            if not df.empty:
                df = df[['Close']].rename(columns={'Close': code})
                df_list.append(df)
                valid_codes.append(code)
            else:
                print(f"Warning: No data for {code}")
        except Exception as e:
            print(f"Error fetching {code}: {e}")

    if not df_list:
        return None, None
    
    # Merge all
    prices_df = pd.concat(df_list, axis=1)
    
    # 2. Handle Listing Dates (Missing Data)
    # We want valid data for ALL columns. dropna() will cut the head until all stocks exist.
    prices_df.dropna(inplace=True) 
    
    if prices_df.empty:
        return None, None
        
    actual_start_date = prices_df.index[0]
    
    return prices_df, actual_start_date

def calculate_portfolio_performance(prices_df, portfolio_targets, rebalance_freq='M'):
    """
    Simulates Rebalancing Portfolio.
    
    Args:
        prices_df: DataFrame of daily prices (columns = codes)
        portfolio_targets: List of dicts [{'code': '..', 'portion': 0.1}, ...]
        rebalance_freq: '2W-FRI', 'ME', '2ME', '3ME' etc.
    
    Returns:
        results: DataFrame with 'Portfolio' and individual code returns (normalized to 1.0)
        cagr: float
        mdd: float
        total_return: float
    """
    
    # 1. Align Targets to DataFrame Columns
    available_codes = prices_df.columns.tolist()
    target_map = { t['code']: float(t['portion']) for t in portfolio_targets if t['code'] in available_codes }
    
    if not target_map:
        return None, 0, 0, 0
    
    # Re-normalize weights
    total_w = sum(target_map.values())
    weights = { k: v/total_w for k, v in target_map.items() }
    
    # 2. Rebalancing Simulation
    
    # Identify Rebalancing Dates
    # Use pandas resample to find end periods.
    # Note: 'ME' is Month End (pandas >= 2.2), 'M' was deprecated but still works.
    # We will assume 'ME' or 'M' style string passed from caller.
    
    try:
        if rebalance_freq.startswith('2W'):
             # 2 Weeks. We use '2W-FRI' usually for bi-weekly.
             rebal_dates = prices_df.resample('2W-FRI').last().index
        else:
             rebal_dates = prices_df.resample(rebalance_freq).last().index
    except Exception as e:
        print(f"Resample Error: {e}, falling back to Monthly")
        rebal_dates = prices_df.resample('ME').last().index

    # Convert to set for fast lookup (normalize to date if needed, but index is timestamp)
    # Actually, business days might differ slightly from calendar ends. 
    # Logic: If today is >= scheduled rebalance date AND we haven't rebalanced yet for that period...
    # Simpler Logic: Check if today is in the rebal_dates set (or closest business day).
    # Since rebal_dates from resample().last() returns the last *available* index in that bucket, 
    # it matches exact trading days in prices_df.
    rebal_dates_set = set(rebal_dates)

    # Initial Investment: 1.0
    current_value = 1.0
    
    # Initial Holdings
    current_holdings = {}
    initial_prices = prices_df.iloc[0]
    for code, w in weights.items():
        current_holdings[code] = (current_value * w) / initial_prices[code]
        
    portfolio_history = []
    dates = prices_df.index
    
    for i, date in enumerate(dates):
        # 2a. Calculate Current Value
        day_prices = prices_df.iloc[i]
        
        day_value = 0.0
        for code, qty in current_holdings.items():
             day_value += qty * day_prices[code]
             
        portfolio_history.append(day_value)
        current_value = day_value
        
        # 2b. Check Rebalancing
        # If this date is a rebalancing date (and not the very last day of data, usually)
        if date in rebal_dates_set and i < len(dates) - 1:
            # Rebalance to target weights
            for code, w in weights.items():
                target_alloc = current_value * w
                current_holdings[code] = target_alloc / day_prices[code]
                
    # 3. Create Result DataFrame
    # Normalize individual prices to 1.0 start
    normalized_prices = prices_df / prices_df.iloc[0]
    
    result_df = normalized_prices.copy()
    result_df['Portfolio'] = portfolio_history
    
    # 4. Calculate Metrics
    # Total Return
    total_return = (portfolio_history[-1] / portfolio_history[0]) - 1
    
    # CAGR (Yr)
    days = (dates[-1] - dates[0]).days
    years = days / 365.25
    cagr = (portfolio_history[-1] / portfolio_history[0]) ** (1/years) - 1 if years > 0 else 0
    
    # MDD
    roll_max = result_df['Portfolio'].cummax()
    daily_drawdown = result_df['Portfolio'] / roll_max - 1.0
    mdd = daily_drawdown.min()
    
    return result_df, cagr, mdd, total_return
