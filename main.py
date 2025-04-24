import requests
from bs4 import BeautifulSoup
import streamlit as st
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the div containing fund data
        fund_data_div = soup.find('div', class_='vTiuKeOU')
        
        if not fund_data_div:
            return {
                'ticker': ticker,
                'status': 'error',
                'message': 'Could not find fund data on page'
            }
        
        # Extract the fund name
        fund_name_element = soup.find('h1', class_='LuOMg9wG')
        fund_name = fund_name_element.text if fund_name_element else ticker
        
        # Initialize data dictionary
        data = {
            'ticker': ticker,
            'name': fund_name,
            'status': 'success'
        }
        
        # Extract data points
        data_items = fund_data_div.find_all('div', class_='J15CnrXn')
        for item in data_items:
            label_div = item.find('div', class_='eYwhIfAy')
            if not label_div:
                continue
                
            label = label_div.get_text(strip=True).replace('.', '')
            
            # Handle different value classes
            value_div = item.find('div', class_='tvV29egN') or item.find('div', class_='YRW3R1in')
            if value_div:
                value = value_div.get_text(strip=True)
                
                # Clean up labels for consistency
                if "Last price" in label:
                    data['last_price'] = value
                elif "1M perf" in label:
                    data['performance_1m'] = value
                elif "1M flows" in label:
                    data['flows_1m'] = value
                elif "AuM" in label:
                    data['aum'] = value
                elif "E/R" in label:
                    data['expense_ratio'] = value
                
                # Look for NAV and NAV change (these might be in different locations)
                nav_div = soup.find('div', string='NAV')
                if nav_div and nav_div.find_next():
                    data['nav'] = nav_div.find_next().get_text(strip=True)
                
                nav_change_div = soup.find('div', string='NAV change')
                if nav_change_div and nav_change_div.find_next():
                    data['nav_change_1d'] = nav_change_div.find_next().get_text(strip=True)
        
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
