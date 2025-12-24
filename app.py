import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
import sys
from main import (
    load_portfolio, 
    load_portfolio_config, 
    fetch_current_status, 
    get_rebalancing_plan,
    execute_plan,
    KISClient
)

# Page Config
st.set_page_config(
    page_title="KIS Rebalancer", 
    page_icon="📈",
    layout="wide"
)

# --- Functions ---
def get_portfolio_files():
    return sorted(glob.glob("portfolio*.yaml"))

# --- Sidebar ---
st.sidebar.title("⚙️ Configuration")
portfolio_files = get_portfolio_files()

if not portfolio_files:
    st.error("No portfolio*.yaml files found in directory.")
    st.stop()

selected_file = st.sidebar.selectbox("Select Portfolio File", portfolio_files)

if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Execution Control")
exec_mode = st.sidebar.radio("Execution Mode", ["split", "market"], index=0, help="Split: 3-step execution to minimize slippage. Market: Immediate execution at current price.")

c1, c2 = st.sidebar.columns(2)
enable_buy = c1.checkbox("Enable BUY")
enable_sell = c2.checkbox("Enable SELL")

if st.sidebar.button("RUN EXECUTION", type="primary"):
    if not (enable_buy or enable_sell):
        st.sidebar.error("Please enable Buy or Sell first.")
    else:
        if 'plan_data' in st.session_state and st.session_state['plan_data']:
             creds = load_portfolio_config(selected_file)
             if creds:
                 client = KISClient(creds)
                 client.get_access_token()
                 
                 place_holder = st.empty()
                 place_holder.info("Executing Orders... Please check the terminal for detailed logs.")
                 
                 # Execute
                 try:
                     # Capture stdout or just let it run (logs go to terminal where user started streamlit)
                     execute_plan(client, st.session_state['plan_data'], exec_mode, enable_buy, enable_sell)
                     place_holder.success("Execution Completed! Refreshing data...")
                     st.cache_data.clear()
                     st.rerun()
                 except Exception as e:
                     place_holder.error(f"Execution Failed: {e}")
        else:
             st.sidebar.error("No plan generated yet. Please wait for data to load.")

# --- Main Page ---
st.title("📈 KIS Rebalancer Dashboard")

if selected_file:
    # Try to load config, but if it returns None (e.g. no config section), 
    # we should likely fallback to env vars if we are using the default portfolio.yaml
    # However, load_portfolio_config returns credential dict. 
    # Logic in main.py: if not os.path.exists -> None. If file exists but no config -> None.
    # Refined logic: If loads None, we assume standard .env loader should take over, 
    # but currently KISClient needs a dict or defaults.
    # Let's manually construct specific creds if load_portfolio_config returns None 
    # but the file exists (meaning just no overrides).
    
    creds = load_portfolio_config(selected_file)
    if not creds:
        # Fallback: Construct from env directly if config missing in yaml
        from dotenv import load_dotenv
        load_dotenv() # Ensure env is loaded
        creds = {
            "APP_KEY": os.getenv("APP_KEY"),
            "APP_SECRET": os.getenv("APP_SECRET"),
            "CANO": os.getenv("CANO"),
            "ACNT_PRDT_CD": os.getenv("ACNT_PRDT_CD"),
            "URL_BASE": os.getenv("URL_BASE", "https://openapi.koreainvestment.com:9443")
        }
        
    if not creds or not creds.get('CANO'):
        st.error(f"Failed to load credentials. Please check .env or portfolio config in {selected_file}")
        st.stop()
        
    client = KISClient(creds)
    
    # 1. Fetching Data
    with st.spinner(f"Connecting to Account {creds.get('CANO')}..."):
        try:
             client.get_access_token()
             summary, holdings, total_asset = fetch_current_status(client)
        except Exception as e:
             st.error(f"Connection Error: {e}")
             st.stop()

    # 2. Summary Metrics
    st.markdown("### 💼 Account Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    if summary:
        tot_amt = float(summary.get('tot_evlu_amt', 0))
        profit = float(summary.get('evlu_pfls_smtl_amt', 0))
        pchs_amt = float(summary.get('pchs_amt_smtl_amt', 0))
        rate_val = (profit / pchs_amt * 100) if pchs_amt > 0 else 0.0
        cash = float(summary.get('dnca_tot_amt', 0))
        
        col1.metric("Total Asset", f"{tot_amt:,.0f} KRW")
        col2.metric("Profit / Loss", f"{profit:,.0f} KRW", f"{rate_val:.2f}%")
        col3.metric("Total Purchased", f"{pchs_amt:,.0f} KRW")
        col4.metric("Deposit (Cash)", f"{cash:,.0f} KRW")
    
    st.divider()

    # 3. Holdings & Charts
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.subheader("📦 Current Holdings")
        if holdings:
            df_holdings = pd.DataFrame(holdings)
            
            # Numeric conversion
            df_holdings['Quantity'] = df_holdings['hldg_qty'].astype(int)
            df_holdings['Current Price'] = df_holdings['prpr'].astype(int)
            df_holdings['Avg Price'] = df_holdings['pchs_avg_pric'].astype(float)
            df_holdings['Eval Value'] = df_holdings['evlu_amt'].astype(float)
            df_holdings['Return'] = df_holdings['evlu_pfls_rt'].astype(float)
            
            # Select & Rename
            df_view = df_holdings[['pdno', 'prdt_name', 'Quantity', 'Avg Price', 'Current Price', 'Return', 'Eval Value']].copy()
            df_view.columns = ['Code', 'Name', 'Qty', 'Avg Price', 'Cur Price', 'Return %', 'Value']
            
            # Calculate Portion
            df_view['Portion'] = (df_view['Value'] / total_asset * 100)
            
            st.dataframe(
                df_view.style.format({
                    'Avg Price': '{:,.0f}', 
                    'Cur Price': '{:,.0f}', 
                    'Value': '{:,.0f}',
                    'Return %': '{:.2f}%',
                    'Portion': '{:.2f}%'
                }), 
                use_container_width=True
            )
        else:
            st.info("No holdings found.")

    with col_right:
        st.subheader("📊 Allocation")
        if holdings and total_asset > 0:
            fig = px.pie(df_view, values='Value', names='Name', hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 4. Rebalancing Plan
    st.subheader("⚖️ Rebalancing Plan")
    
    with st.spinner("Calculating Rebalancing Plan (This may take a moment)..."):
        # We pass 'holdings' to reuse the list but re-calculation inside uses fresh asking prices mostly?
        # Actually our `get_rebalancing_plan` calls API.
        plan_data = get_rebalancing_plan(client, selected_file, total_asset, holdings)
        st.session_state['plan_data'] = plan_data
        
        if plan_data:
            df_plan = pd.DataFrame(plan_data)
            
            # Display Columns
            df_display = df_plan[['code', 'name', 'target_portion', 'target_amt', 'current_amt', 'diff', 'action', 'qty', 'est_price']].copy()
            
            # Formatting for display
            df_display['target_portion'] = df_display['target_portion'] * 100
            
            # Rename Columns first
            df_display.rename(columns={
                'code': 'Code', 'name': 'Name', 'target_portion': 'Target %', 
                'target_amt': 'Target Amt', 'current_amt': 'Current Amt', 
                'diff': 'Diff', 'action': 'Action', 'qty': 'Qty', 'est_price': 'Est. Price'
            }, inplace=True)

            # Styling
            def highlight_action(val):
                color = ''
                if val == 'BUY': color = 'background-color: #d4edda; color: #155724' # Light Green
                elif val == 'SELL': color = 'background-color: #f8d7da; color: #721c24' # Light Red
                return color

            st.dataframe(
                df_display.style.map(highlight_action, subset=['Action'])
                .format({
                    'Target %': '{:.1f}%',
                    'Target Amt': '{:,.0f}',
                    'Current Amt': '{:,.0f}',
                    'Diff': '{:+,.0f}',
                    'Qty': '{:,.0f}',
                    'Est. Price': '{:,.0f}'
                }),
                use_container_width=True,
                height=600
            )
            
            # Summary of Actions
            buy_cnt = len([x for x in plan_data if x['action'] == 'BUY' and x['qty'] > 0])
            sell_cnt = len([x for x in plan_data if x['action'] == 'SELL' and x['qty'] > 0])
            
            st.info(f"📋 Plan Summary: {buy_cnt} BUY orders, {sell_cnt} SELL orders ready using '{exec_mode}' mode.")
            
        else:
            st.warning("No rebalancing targets found in portfolio file.")

    # 5. Backtest Tab
    st.divider()
    st.header("📊 Backtest Simulation")

    with st.expander("Backtest Configuration", expanded=True):
        bt_col1, bt_col2, bt_col3 = st.columns(3)
        bt_years = bt_col1.selectbox("Period", [1, 3, 5], index=1, format_func=lambda x: f"{x} Year(s)")
        
        freq_map = {
            "2 Weeks": "2W-FRI",
            "Monthly (End)": "ME", 
            "2 Months (End)": "2ME", 
            "3 Months (End)": "3ME"
        }
        bt_freq_label = bt_col2.selectbox("Rebalancing Interval", list(freq_map.keys()), index=1)
        bt_freq = freq_map[bt_freq_label]
        
        # bt_col3.info(f"Strategy: {bt_freq_label} Rebalancing")
        
        run_bt = st.button("Run Backtest")

    if run_bt:
        from backtest_logic import fetch_history, calculate_portfolio_performance
        
        # Prepare targets
        targets = load_portfolio(selected_file)
        if not targets:
            st.warning("No targets to backtest.")
        else:
            codes = [str(t['code']) for t in targets]
            
            with st.spinner("Fetching historical data..."):
                prices_df, start_date = fetch_history(codes, years=bt_years)
                
            if prices_df is None or prices_df.empty:
                st.error("Failed to fetch historical data. Some symbols (e.g. Gold) might fail with public Yahoo data.")
            else:
                # Calculate
                results, cagr, mdd, total_ret = calculate_portfolio_performance(prices_df, targets, rebalance_freq=bt_freq)
                
                if results is not None:
                    # Metrics
                    m_col1, m_col2, m_col3 = st.columns(3)
                    m_col1.metric("CAGR", f"{cagr*100:.2f}%")
                    m_col2.metric("Max Drawdown (MDD)", f"{mdd*100:.2f}%")
                    m_col3.metric("Total Return", f"{total_ret*100:.2f}%")
                    
                    st.success(f"Backtest Period: {start_date.strftime('%Y-%m-%d')} ~ {prices_df.index[-1].strftime('%Y-%m-%d')}")
                    if start_date.year > (pd.Timestamp.today() - pd.DateOffset(years=bt_years)).year:
                         st.warning("⚠️ Note: Backtest start date was adjusted due to data availability (some ETFs were listed later).")

                    # Chart
                    # Use Plotly for custom axis formatting
                    fig_perf = px.line(results, y='Portfolio', title='Portfolio Cumulative Return')
                    fig_perf.update_xaxes(
                        tickformat="%Y-%m",
                        dtick="M1" if bt_years == 1 else "M3" # Adjust density based on duration
                    )
                    st.plotly_chart(fig_perf, use_container_width=True)
                    
                    # Individual Assets (Optional)
                    with st.expander("Show Individual Assets Performance"):
                         # Rename columns for display: Code -> Name
                         ind_df = results.drop(columns=['Portfolio'])
                         
                         name_map = { str(t['code']): t['name'] for t in targets }
                         ind_df.rename(columns=name_map, inplace=True)
                         
                         fig_ind = px.line(ind_df)
                         fig_ind.update_xaxes(tickformat="%Y-%m")
                         st.plotly_chart(fig_ind, use_container_width=True)
                else:
                    st.error("Simulation failed.")
