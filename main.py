import yfinance as yf
import streamlit as st
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import plotly.graph_objects as go
import random
import requests
from requests.exceptions import HTTPError, RequestException
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set page configuration
st.set_page_config(
    page_title="Fund Tracker - Yahoo Finance",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS for the minimalist card design
st.markdown("""
<style>
.fund-card {
    background-color: #f9f9f9;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 20px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
.fund-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 10px;
    border-bottom: 1px solid #eaeaea;
    padding-bottom: 10px;
}
.fund-title {
    font-size: 20px;
    font-weight: bold;
    color: #333;
}
.fund-subtitle {
    font-size: 14px;
    color: #666;
}
.fund-data {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
}
.data-item {
    padding: 5px 0;
}
.data-label {
    font-size: 12px;
    color: #666;
}
.data-value {
    font-size: 16px;
    font-weight: 500;
    color: #333;
}
.positive-value {
    color: #28a745;
}
.negative-value {
    color: #dc3545;
}
.last-updated {
    font-size: 12px;
    color: #999;
    text-align: right;
    margin-top: 5px;
}
</style>
""", unsafe_allow_html=True)

# List of fund tickers to track
FUND_TICKERS = [
    'TSLI.L', 'YGLD.DE', 'SPYY.L', 'GOOI.L', 'QQQY.L', 
    'COIY.L', 'METY.L', 'ONVD.DE', 'OAMZ.DE', 'AAPY.DE', 'YMSF.DE'
]

# Cache for ticker data to avoid repeated API calls
if 'ticker_cache' not in st.session_state:
    st.session_state.ticker_cache = {}
    st.session_state.cache_timestamp = {}

def format_currency(value, currency_symbol='$'):
    """Format a number as currency."""
    if pd.isna(value):
        return "N/A"
    return f"{currency_symbol}{value:,.2f}"

def format_percentage(value):
    """Format a number as percentage."""
    if pd.isna(value):
        return "N/A"
    return f"{value:.2f}%" if value >= 0 else f"{value:.2f}%"

def get_currency_symbol(ticker):
    """Get currency symbol based on ticker suffix."""
    if ticker.endswith('.L'):
        return '£'
    elif ticker.endswith('.DE'):
        return '€'
    else:
        return '$'

def fetch_with_retry(ticker_obj, method_name, *args, max_retries=3, **kwargs):
    """Fetch data with retry logic and exponential backoff."""
    retries = 0
    while retries < max_retries:
        try:
            # Add a random delay to avoid rate limiting
            time.sleep(random.uniform(0.5, 2.0))
            
            # Get the method to call
            method = getattr(ticker_obj, method_name)
            return method(*args, **kwargs)
        except (HTTPError, RequestException) as e:
            if "429" in str(e):  # Too Many Requests
                wait_time = (2 ** retries) + random.random()
                logging.warning(f"Rate limit hit for {ticker_obj.ticker}. Waiting {wait_time:.2f}s before retry {retries+1}/{max_retries}")
                time.sleep(wait_time)
                retries += 1
            else:
                raise
    
    # If we've exhausted retries
    raise Exception(f"Failed to fetch {method_name} for {ticker_obj.ticker} after {max_retries} retries")

def get_fund_data(ticker):
    """Fetch fund data for a given ticker using yfinance with caching and retries."""
    # Check cache first
    current_time = time.time()
    cache_time = st.session_state.cache_timestamp.get(ticker, 0)
    cache_age = current_time - cache_time
    
    # Use cache if it's less than 15 minutes old
    if ticker in st.session_state.ticker_cache and cache_age < 900:  # 15 minutes
        return st.session_state.ticker_cache[ticker]
    
    try:
        # Get ticker info
        ticker_obj = yf.Ticker(ticker)
        
        try:
            # Try to get info with retries
            info = {}
            try:
                info = fetch_with_retry(ticker_obj, 'info')
            except Exception as e:
                logging.warning(f"Failed to get full info for {ticker}: {str(e)}")
                # Fall back to basics if we can't get full info
                pass
            
            # Get currency symbol
            currency_symbol = get_currency_symbol(ticker)
            
            # Calculate dates for historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=35)  # Get a bit more than 1 month
            
            # Get historical data with retries
            hist = None
            try:
                hist = fetch_with_retry(ticker_obj, 'history', start=start_date, end=end_date)
            except Exception as e:
                logging.warning(f"Failed to get history for {ticker}: {str(e)}")
                hist = pd.DataFrame()  # Empty DataFrame as fallback
            
            # Calculate last price
            last_price = None
            if not hist.empty:
                last_price = hist['Close'].iloc[-1]
            
            # Calculate 1-month performance
            perf_1m = None
            if not hist.empty and len(hist) > 20:  # Need enough data points
                # Try to get price from approximately 1 month ago
                first_price = hist['Close'].iloc[0]
                perf_1m = ((last_price - first_price) / first_price) * 100 if first_price else None
            
            # Calculate 1-day change
            change_1d = None
            if not hist.empty and len(hist) > 1:
                prev_day_price = hist['Close'].iloc[-2]
                change_1d = ((last_price - prev_day_price) / prev_day_price) * 100 if prev_day_price else None
            
            # Get name
            name = info.get('shortName', info.get('longName', ticker.split('.')[0]))
            
            # Format market cap as AuM (Assets under Management)
            market_cap = info.get('marketCap')
            if market_cap:
                if market_cap >= 1_000_000_000:
                    aum = f"{currency_symbol}{market_cap / 1_000_000_000:.2f}B"
                elif market_cap >= 1_000_000:
                    aum = f"{currency_symbol}{market_cap / 1_000_000:.2f}M"
                else:
                    aum = f"{currency_symbol}{market_cap / 1_000:.2f}K"
            else:
                aum = "N/A"
            
            # Get expense ratio if available
            expense_ratio = info.get('annualReportExpenseRatio', info.get('totalExpenseRatio', None))
            if expense_ratio is None:
                expense_ratio = None
            else:
                # Convert to percentage
                expense_ratio = expense_ratio * 100
            
            result = {
                'ticker': ticker,
                'name': name,
                'last_price': last_price,
                'currency_symbol': currency_symbol,
                'performance_1m': perf_1m,
                'nav_change_1d': change_1d,
                'nav': last_price,  # Using last price as NAV
                'aum': aum,
                'expense_ratio': expense_ratio,
                'status': 'success'
            }
            
            # Store in cache
            st.session_state.ticker_cache[ticker] = result
            st.session_state.cache_timestamp[ticker] = current_time
            
            return result
            
        except Exception as e:
            logging.error(f"Error processing {ticker} data: {str(e)}")
            return {
                'ticker': ticker,
                'status': 'error',
                'message': f"Data processing error: {str(e)}"
            }
    
    except Exception as e:
        logging.error(f"Failed to initialize ticker {ticker}: {str(e)}")
        return {
            'ticker': ticker,
            'status': 'error',
            'message': str(e)
        }

def fetch_sequentially(tickers):
    """Fetch ticker data sequentially to avoid rate limiting."""
    results = []
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        # Update progress
        progress = (i / len(tickers))
        progress_bar.progress(progress, f"Fetching {ticker}...")
        
        # Fetch data with delay between requests
        result = get_fund_data(ticker)
        results.append(result)
        
        # Small delay between requests
        time.sleep(random.uniform(1.0, 2.0))
    
    progress_bar.progress(1.0)
    return results

def display_fund_cards(fund_data_list):
    """Display the fund data in a minimalistic card design."""
    # Create 3 columns
    cols = st.columns(3)
    
    # Group funds by columns
    for i, fund_data in enumerate(fund_data_list):
        col_idx = i % 3
        
        with cols[col_idx]:
            if fund_data['status'] == 'success':
                # Format values
                currency_symbol = fund_data.get('currency_symbol', '$')
                last_price = format_currency(fund_data.get('last_price'), currency_symbol) if fund_data.get('last_price') is not None else "N/A"
                perf_1m = format_percentage(fund_data.get('performance_1m')) if fund_data.get('performance_1m') is not None else "N/A"
                nav_change_1d = format_percentage(fund_data.get('nav_change_1d')) if fund_data.get('nav_change_1d') is not None else "N/A"
                nav = format_currency(fund_data.get('nav'), currency_symbol) if fund_data.get('nav') is not None else "N/A"
                aum = fund_data.get('aum', "N/A")
                expense_ratio = format_percentage(fund_data.get('expense_ratio')) if fund_data.get('expense_ratio') is not None else "N/A"
                
                # Format the card HTML
                html = f"""
                <div class="fund-card">
                    <div class="fund-header">
                        <div>
                            <div class="fund-title">{fund_data['ticker']}</div>
                            <div class="fund-subtitle">{fund_data.get('name', '')}</div>
                        </div>
                    </div>
                    <div class="fund-data">
                """
                
                # Last price
                html += f"""
                    <div class="data-item">
                        <div class="data-label">Last Price</div>
                        <div class="data-value">{last_price}</div>
                    </div>
                """
                
                # 1M Performance
                perf_class = "positive-value" if fund_data.get('performance_1m', 0) >= 0 else "negative-value"
                html += f"""
                    <div class="data-item">
                        <div class="data-label">1M Performance</div>
                        <div class="data-value {perf_class}">{perf_1m}</div>
                    </div>
                """
                
                # AuM
                html += f"""
                    <div class="data-item">
                        <div class="data-label">AuM</div>
                        <div class="data-value">{aum}</div>
                    </div>
                """
                
                # Expense Ratio
                html += f"""
                    <div class="data-item">
                        <div class="data-label">Expense Ratio</div>
                        <div class="data-value">{expense_ratio}</div>
                    </div>
                """
                
                # NAV
                html += f"""
                    <div class="data-item">
                        <div class="data-label">NAV</div>
                        <div class="data-value">{nav}</div>
                    </div>
                """
                
                # 1D NAV Change
                change_class = "positive-value" if fund_data.get('nav_change_1d', 0) >= 0 else "negative-value"
                html += f"""
                    <div class="data-item">
                        <div class="data-label">1D NAV Change</div>
                        <div class="data-value {change_class}">{nav_change_1d}</div>
                    </div>
                """
                
                # Close the card
                html += f"""
                    </div>
                    <div class="last-updated">Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                """
                
                st.markdown(html, unsafe_allow_html=True)
                
                # Add price chart button (load chart only when clicked)
                if st.button(f"View {fund_data['ticker']} Chart", key=f"chart_{fund_data['ticker']}"):
                    try:
                        # Get historical data for the past 6 months
                        ticker_obj = yf.Ticker(fund_data['ticker'])
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=180)
                        
                        with st.spinner(f"Loading chart for {fund_data['ticker']}..."):
                            # Add delay to avoid rate limiting
                            time.sleep(random.uniform(0.5, 1.5))
                            hist = ticker_obj.history(start=start_date, end=end_date)
                        
                        if not hist.empty:
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=hist.index,
                                y=hist['Close'],
                                mode='lines',
                                name='Close Price',
                                line=dict(color='royalblue', width=2)
                            ))
                            fig.update_layout(
                                title=f"{fund_data['ticker']} - 6 Month Price History",
                                xaxis_title="Date",
                                yaxis_title=f"Price ({currency_symbol})",
                                height=400,
                                margin=dict(l=0, r=0, t=40, b=0)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No historical data available for chart.")
                    except Exception as e:
                        st.error(f"Error loading chart: {str(e)}")
            else:
                # Display error card
                st.error(f"Error fetching data for {fund_data['ticker']}: {fund_data.get('message', 'Unknown error')}")

def display_table_view(fund_data_list):
    """Display fund data in a sortable table format."""
    # Extract successful data
    valid_data = [data for data in fund_data_list if data['status'] == 'success']
    
    if not valid_data:
        st.warning("No valid fund data available for table view.")
        return
    
    # Prepare data for pandas DataFrame
    table_data = []
    for fund in valid_data:
        currency_symbol = fund.get('currency_symbol', '$')
        row = {
            'Ticker': fund['ticker'],
            'Name': fund.get('name', ''),
            'Last Price': format_currency(fund.get('last_price'), currency_symbol) if fund.get('last_price') is not None else "N/A",
            '1M Performance': format_percentage(fund.get('performance_1m')) if fund.get('performance_1m') is not None else "N/A",
            'AuM': fund.get('aum', 'N/A'),
            'Expense Ratio': format_percentage(fund.get('expense_ratio')) if fund.get('expense_ratio') is not None else "N/A",
            'NAV': format_currency(fund.get('nav'), currency_symbol) if fund.get('nav') is not None else "N/A",
            '1D NAV Change': format_percentage(fund.get('nav_change_1d')) if fund.get('nav_change_1d') is not None else "N/A"
        }
        table_data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(table_data)
    
    # Display table
    st.dataframe(df)
    
    # Add a chart showing comparative performance (only if clicked)
    if st.button("Show Performance Comparison Chart"):
        # Create dataframe for chart
        perf_data = {
            'Ticker': [],
            'Performance (%)': []
        }
        
        for fund in valid_data:
            if fund.get('performance_1m') is not None:
                perf_data['Ticker'].append(fund['ticker'])
                perf_data['Performance (%)'].append(fund.get('performance_1m', 0))
        
        if perf_data['Ticker']:
            perf_df = pd.DataFrame(perf_data)
            fig = go.Figure()
            colors = ['#28a745' if x >= 0 else '#dc3545' for x in perf_df['Performance (%)']]
            
            fig.add_trace(go.Bar(
                x=perf_df['Ticker'],
                y=perf_df['Performance (%)'],
                marker_color=colors,
                text=perf_df['Performance (%)'].apply(lambda x: f"{x:.2f}%"),
                textposition='auto'
            ))
            
            fig.update_layout(
                title="1-Month Performance Comparison",
                xaxis_title="Fund",
                yaxis_title="Performance (%)",
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No performance data available for comparison chart.")

def main():
    # App title and description
    st.title("📊 Fund Data Tracker")
    st.markdown("Real-time data for selected funds from Yahoo Finance")
    
    # Add settings sidebar
    with st.sidebar:
        st.header("Settings")
        cache_duration = st.slider(
            "Cache Duration (minutes)", 
            min_value=5, 
            max_value=60, 
            value=15,
            help="How long to keep fund data in cache before refreshing"
        )
        fetch_method = st.radio(
            "Data Fetch Method",
            options=["Sequential (Slower but Reliable)", "Parallel (Faster but May Hit Rate Limits)"],
            index=0,
            help="Choose how to fetch data from Yahoo Finance"
        )
    
    # Add a refresh button and view toggle
    col1, col2 = st.columns([1, 4])
    with col1:
        refresh = st.button("🔄 Refresh Data")
    with col2:
        view_mode = st.radio("View Mode:", ("Cards", "Table"), horizontal=True)
    
    # Create a placeholder for the fund data
    fund_data_container = st.empty()
    
    # Session state to store fund data
    if 'fund_data' not in st.session_state or refresh:
        with st.spinner("Fetching latest fund data..."):
            if fetch_method.startswith("Sequential"):
                st.session_state.fund_data = fetch_sequentially(FUND_TICKERS)
            else:
                with ThreadPoolExecutor(max_workers=3) as executor:
                    st.session_state.fund_data = list(executor.map(get_fund_data, FUND_TICKERS))
            st.session_state.last_updated = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Display last updated time
    st.caption(f"Last updated: {st.session_state.last_updated}")
    
    # Display fund data based on selected view mode
    with fund_data_container:
        if view_mode == "Cards":
            display_fund_cards(st.session_state.fund_data)
        else:
            display_table_view(st.session_state.fund_data)
    
    # Add footer with credits
    st.markdown("---")
    st.caption("Data source: Yahoo Finance")

if __name__ == "__main__":
    main()
