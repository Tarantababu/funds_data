import requests
from bs4 import BeautifulSoup
import streamlit as st
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import re

# Set page configuration
st.set_page_config(
    page_title="Fund Tracker",
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
    "TSLI", "YGLD", "SPYY", "GOOI", "QQQY", 
    "COIY", "METY", "ONVD", "OAMZ", "AAPY", "YMSF"
]

# Base URL for the funds
BASE_URL = "https://www.trackinsight.com/en/fund/"

def get_fund_data(ticker):
    """Fetch and parse fund data for a given ticker."""
    url = f"{BASE_URL}{ticker}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.trackinsight.com/en/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {
                'ticker': ticker,
                'status': 'error',
                'message': f'HTTP error: {response.status_code}'
            }
        
        # Save HTML content to debug
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # First, try to find the fund name
        fund_name_element = soup.find('h1')
        fund_name = fund_name_element.text.strip() if fund_name_element else ticker
        
        # Initialize data dictionary
        data = {
            'ticker': ticker,
            'name': fund_name,
            'status': 'success'
        }
        
        # Find all potential data containers
        # Look for divs that contain labels like "Last price", "1M perf", etc.
        
        # Method 1: Find by text content
        last_price = None
        performance_1m = None
        flows_1m = None
        aum = None
        expense_ratio = None
        nav = None
        nav_change_1d = None
        
        # Extract data by finding relevant text labels
        for div in soup.find_all('div'):
            text_content = div.get_text(strip=True)
            
            # Last price
            if text_content == "Last price":
                next_div = div.find_next('div')
                if next_div:
                    last_price = next_div.get_text(strip=True)
                    data['last_price'] = last_price
            
            # 1M performance
            elif text_content == "1M perf." or text_content == "1M perf":
                next_div = div.find_next('div')
                if next_div:
                    performance_1m = next_div.get_text(strip=True)
                    data['performance_1m'] = performance_1m
            
            # 1M flows
            elif text_content == "1M flows":
                next_div = div.find_next('div')
                if next_div:
                    flows_1m = next_div.get_text(strip=True)
                    data['flows_1m'] = flows_1m
            
            # AuM
            elif text_content == "AuM":
                next_div = div.find_next('div')
                if next_div:
                    aum = next_div.get_text(strip=True)
                    data['aum'] = aum
            
            # Expense Ratio
            elif text_content == "E/R":
                next_div = div.find_next('div')
                if next_div:
                    expense_ratio = next_div.get_text(strip=True)
                    data['expense_ratio'] = expense_ratio
            
            # NAV
            elif text_content == "NAV":
                next_div = div.find_next('div')
                if next_div:
                    nav = next_div.get_text(strip=True)
                    data['nav'] = nav
            
            # NAV change
            elif "NAV change" in text_content:
                next_div = div.find_next('div')
                if next_div:
                    nav_change_1d = next_div.get_text(strip=True)
                    data['nav_change_1d'] = nav_change_1d
        
        # Method 2: Try to find the data by pattern matching
        if not last_price:
            # Look for currency symbols followed by numbers
            currency_pattern = re.compile(r'[\$€£¥]\s*[\d,]+\.?\d*')
            for div in soup.find_all('div'):
                text = div.get_text(strip=True)
                if currency_pattern.match(text):
                    data['last_price'] = text
                    break
        
        # Alternative method: Try looking for specific CSS classes
        # This is a fallback in case the site structure has completely changed
        for div in soup.find_all('div', class_=lambda c: c and ('Price' in c or 'price' in c)):
            parent_div = div.parent
            if parent_div:
                value_div = parent_div.find_next('div')
                if value_div:
                    data['last_price'] = value_div.get_text(strip=True)
        
        # If we couldn't find any data, mark as error
        if len(data) <= 3:  # Only ticker, name, and status
            return {
                'ticker': ticker,
                'status': 'error',
                'message': 'Could not find fund data on page'
            }
        
        return data
    
    except Exception as e:
        return {
            'ticker': ticker,
            'status': 'error',
            'message': str(e)
        }

def fetch_all_fund_data():
    """Fetch data for all funds in parallel."""
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(get_fund_data, FUND_TICKERS))
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
                # Format the card HTML
                html = f"""
                <div class="fund-card">
                    <div class="fund-header">
                        <div class="fund-title">{fund_data['ticker']} - {fund_data.get('name', '')}</div>
                    </div>
                    <div class="fund-data">
                """
                
                # Last price
                if 'last_price' in fund_data:
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">Last Price</div>
                            <div class="data-value">{fund_data['last_price']}</div>
                        </div>
                    """
                
                # 1M Performance
                if 'performance_1m' in fund_data:
                    value_class = "positive-value" if "+" in fund_data['performance_1m'] else "negative-value" if "-" in fund_data['performance_1m'] else ""
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">1M Performance</div>
                            <div class="data-value {value_class}">{fund_data['performance_1m']}</div>
                        </div>
                    """
                
                # 1M Flows
                if 'flows_1m' in fund_data:
                    value_class = "positive-value" if "+" in fund_data['flows_1m'] else "negative-value" if "-" in fund_data['flows_1m'] else ""
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">1M Flows</div>
                            <div class="data-value {value_class}">{fund_data['flows_1m']}</div>
                        </div>
                    """
                
                # AuM
                if 'aum' in fund_data:
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">AuM</div>
                            <div class="data-value">{fund_data['aum']}</div>
                        </div>
                    """
                
                # Expense Ratio
                if 'expense_ratio' in fund_data:
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">Expense Ratio</div>
                            <div class="data-value">{fund_data['expense_ratio']}</div>
                        </div>
                    """
                
                # NAV
                if 'nav' in fund_data:
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">NAV</div>
                            <div class="data-value">{fund_data['nav']}</div>
                        </div>
                    """
                
                # 1D NAV Change
                if 'nav_change_1d' in fund_data:
                    value_class = "positive-value" if "+" in fund_data.get('nav_change_1d', '') else "negative-value" if "-" in fund_data.get('nav_change_1d', '') else ""
                    html += f"""
                        <div class="data-item">
                            <div class="data-label">1D NAV Change</div>
                            <div class="data-value {value_class}">{fund_data['nav_change_1d']}</div>
                        </div>
                    """
                
                # Close the card
                html += f"""
                    </div>
                    <div class="last-updated">Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                """
                
                st.markdown(html, unsafe_allow_html=True)
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
        row = {
            'Ticker': fund['ticker'],
            'Name': fund.get('name', ''),
            'Last Price': fund.get('last_price', ''),
            '1M Performance': fund.get('performance_1m', ''),
            '1M Flows': fund.get('flows_1m', ''),
            'AuM': fund.get('aum', ''),
            'Expense Ratio': fund.get('expense_ratio', ''),
            'NAV': fund.get('nav', ''),
            '1D NAV Change': fund.get('nav_change_1d', '')
        }
        table_data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(table_data)
    
    # Display table
    st.dataframe(df)

def main():
    # App title and description
    st.title("📊 Fund Data Tracker")
    st.markdown("Real-time data for selected funds from TrackInsight")
    
    # Add debugging options
    with st.expander("Debug Options"):
        debug_ticker = st.selectbox("Test single ticker", [""] + FUND_TICKERS)
        if st.button("Test Fetch"):
            if debug_ticker:
                with st.spinner(f"Testing fetch for {debug_ticker}..."):
                    result = get_fund_data(debug_ticker)
                    st.json(result)
    
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
            st.session_state.fund_data = fetch_all_fund_data()
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
    st.caption("Data source: TrackInsight.com")

if __name__ == "__main__":
    main()
