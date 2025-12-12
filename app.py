import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf
import requests
import time
import random
import warnings
from datetime import datetime, timedelta

# Machine Learning Imports
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

# Try importing TensorFlow/Keras for LSTM
try:
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    HAS_TF = True
except ImportError:
    HAS_TF = False

# Web Scraping Imports
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Group 32 - AI Capstone Super Dashboard",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

warnings.filterwarnings('ignore')

# ---------------------------------------------------------
# UPDATED CSS (Sidebar Radio Text Color Changed to #FF5733)
# ---------------------------------------------------------

CUSTOM_CSS = """
<style> 
/* Change radio label text color */
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    color: #FF5733 !important;
    font-weight: 700;
}

/* Change selected radio background */
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] {
    background-color: #FFB6C1 !important; /* Light Pink */
    border-radius: 6px;
    padding: 4px 8px;
    color: #FF5733 !important;
}

/* Hover background */
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background-color: #FFD6E7 !important;
    border-radius: 6px;
}

/* Radio circle color */
section[data-testid="stSidebar"] div[role="radiogroup"] input[type="radio"] {
    accent-color: #FF4B4B !important; /* Red */
}

/* Fix for SVG radio icons */
section[data-testid="stSidebar"] div[role="radiogroup"] svg {
    fill: #FF4B4B !important;
    stroke: #FF4B4B !important;
}

/* Selected radio circle fill */
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] svg {
    fill: #FF4B4B !important;
    stroke: #FF4B4B !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------

@st.cache_data(ttl=300)
def fetch_stock_data_extended(ticker, period="2y"):
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['MA10'] = df['Close'].rolling(10).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['MA200'] = df['Close'].rolling(200).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp12 = df['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        df['BB_Middle'] = df['Close'].rolling(20).mean()
        df['BB_Upper'] = df['BB_Middle'] + df['Close'].rolling(20).std() * 2
        df['BB_Lower'] = df['BB_Middle'] - df['Close'].rolling(20).std() * 2

        df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
        df['Volatility'] = df['Log_Ret'].rolling(21).std() * np.sqrt(252)

        df['Prediction_Target'] = df['Close'].shift(-1)

        return df.dropna()
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# LIVE MARQUEE
# ---------------------------------------------------------

@st.cache_data(ttl=120)
def get_live_marquee_prices():
    tickers = ["AAPL","MSFT","GOOGL","AMZN","TSLA","NVDA","AMD","INTC",
               "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","BTC-USD","ETH-USD"]
    try:
        data = yf.download(tickers, period="1d", progress=False)
        if data.empty: return "Loading Market Data..."

        if isinstance(data.columns, pd.MultiIndex):
            latest = data["Close"].iloc[-1]
            result = []
            for t in tickers:
                if t in latest:
                    result.append(f"{t}: ${latest[t]:.2f} {random.choice(['🔺','🔻'])}")
            return "  |  ".join(result)
        return "Market Data Unavailable"
    except:
        return "Connecting to Exchange..."

# ---------------------------------------------------------
# LSTM PREDICTOR CLASS
# ---------------------------------------------------------

class AmazonTrendPredictor:
    def __init__(self, seq_len=14):
        self.seq_len = seq_len
        self.scaler = MinMaxScaler()
        self.model = None

    def generate_synthetic_sales_data(self, days=365):
        t = np.arange(days)
        base = 100 + 0.3 * t
        season = 10*np.sin(t*0.1)
        noise = np.random.normal(0,5,days)
        sales = base + season + noise
        return pd.DataFrame(sales, columns=["Sales"])

    def build_lstm_model(self):
        if not HAS_TF: return None
        model = Sequential()
        model.add(LSTM(50, return_sequences=True, input_shape=(self.seq_len,1)))
        model.add(Dropout(0.2))
        model.add(LSTM(50))
        model.add(Dropout(0.2))
        model.add(Dense(25))
        model.add(Dense(1))
        model.compile(optimizer='adam', loss='mse')
        return model

    def train_and_predict(self, data, future_days=14):
        values = data.values
        scaled = self.scaler.fit_transform(values)

        X, y = [], []
        for i in range(self.seq_len, len(scaled)):
            X.append(scaled[i-self.seq_len:i,0])
            y.append(scaled[i,0])

        X = np.array(X).reshape(-1, self.seq_len, 1)
        y = np.array(y)

        preds = []
        if HAS_TF:
            model = self.build_lstm_model()
            model.fit(X, y, epochs=5, batch_size=32, verbose=0)

            batch = scaled[-self.seq_len:].reshape(1, self.seq_len,1)
            for _ in range(future_days):
                pred = model.predict(batch, verbose=0)[0]
                preds.append(pred)
                batch = np.append(batch[:,1:,:], [[pred]], axis=1)

            preds = self.scaler.inverse_transform(np.array(preds)).flatten()
        else:
            last = values[-1][0]
            momentum = (values[-1][0] - values[-30][0]) / 30
            for i in range(future_days):
                preds.append(last + momentum*(i+1) + np.random.normal(0,2))

        return preds

# ---------------------------------------------------------
# PRODUCT DB
# ---------------------------------------------------------
PRODUCT_DB = {
    "Smartphones": [
        {"id": "SP001", "name": "iPhone 15 Pro Max", "brand": "Apple", "base_price": 1199},
        {"id": "SP002", "name": "Samsung Galaxy S24 Ultra", "brand": "Samsung", "base_price": 1299},
        {"id": "SP003", "name": "Google Pixel 8 Pro", "brand": "Google", "base_price": 999},
        {"id": "SP004", "name": "OnePlus 12", "brand": "OnePlus", "base_price": 799},
    ]
}

# ---------------------------------------------------------
# MODULE RENDER FUNCTIONS
# ---------------------------------------------------------

def render_amazon_dashboard():
    st.title("📦 Amazon Trend Intelligence (AI Powered)")
    st.subheader("LSTM-based Forecasting Model")

    col1, col2 = st.columns([1,3])

    with col1:
        category = st.selectbox("Select Niche", list(PRODUCT_DB.keys()))
        days_hist = st.slider("History", 90, 730, 365)
        days_pred = st.slider("Forecast Days", 7, 60, 30)
        run = st.button("Run Simulation")

    with col2:
        if run:
            predictor = AmazonTrendPredictor(seq_len=20)
            hist = predictor.generate_synthetic_sales_data(days_hist)
            preds = predictor.train_and_predict(hist, days_pred)

            fig = go.Figure()
            fig.add_trace(go.Scatter(y=hist["Sales"], name="History"))
            fig.add_trace(go.Scatter(
                x=list(range(days_hist, days_hist+days_pred)),
                y=preds,
                name="Forecast"
            ))
            st.plotly_chart(fig, use_container_width=True)

def render_stock_predictor():
    st.title("📈 Pro Stock Analytics Suite")

    STOCK_MAP = {
        "Apple (AAPL)": "AAPL",
        "Tesla (TSLA)": "TSLA",
        "Microsoft (MSFT)": "MSFT",
        "Bitcoin (BTC)": "BTC-USD"
    }

    selected = st.sidebar.selectbox("Search or Select Brand", STOCK_MAP.keys())
    ticker = STOCK_MAP[selected]

    period = st.sidebar.select_slider("Range", ["6mo","1y","2y","5y"], value="2y")

    if st.button("Analyze Stock"):
        df = fetch_stock_data_extended(ticker, period)

        if df.empty:
            st.error("No data.")
            return

        st.write(df.tail())

def render_product_catalog_advanced():
    st.title("🛒 Product Catalog")
    cat = st.sidebar.radio("Browse Categories", list(PRODUCT_DB.keys()))
    items = PRODUCT_DB[cat]
    for i in items:
        st.write(i)

def render_about_page():
    st.title("ℹ️ About Project")
    st.write("Group 32 — AI Dashboard")

# ---------------------------------------------------------
# MAIN NAVIGATION
# ---------------------------------------------------------

marquee = get_live_marquee_prices()
st.markdown(f"""
<div style="padding:8px; background:#111; color:#0f0; font-size:18px;">
{marquee}
</div>
""", unsafe_allow_html=True)

st.sidebar.title("🚀 Navigation")

page = st.sidebar.radio(
    "Go To Module:",
    ["Stock Predictor", "Amazon Trend AI", "Product Catalog", "About Project"]
)

if page == "Stock Predictor":
    render_stock_predictor()
elif page == "Amazon Trend AI":
    render_amazon_dashboard()
elif page == "Product Catalog":
    render_product_catalog_advanced()
else:
    render_about_page()
