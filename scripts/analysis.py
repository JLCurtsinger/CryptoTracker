from datetime import datetime, timezone
import json
import requests
import numpy as np
import os
import pandas as pd

# =============================================
# API KEYS & ENDPOINTS
# =============================================
API_KEY = os.environ.get('COINMARKETCAP_API_KEY')
if not API_KEY:
    raise ValueError("No API key found in environment variable.")

BASE_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
COINBASE_PRODUCTS_URL = 'https://api.exchange.coinbase.com/products'

# =============================================
# FETCH COINBASE SYMBOLS
# =============================================
def fetch_coinbase_symbols():
    """
    Fetches the list of tradable products (pairs) from Coinbase Exchange
    and returns a set of the base currencies (e.g., 'BTC', 'ETH', etc.).
    """
    try:
        response = requests.get(COINBASE_PRODUCTS_URL)
        if response.status_code != 200:
            print(f"Error fetching Coinbase products. HTTP {response.status_code}")
            return set()
        products = response.json()
    except Exception as e:
        print(f"Exception while fetching Coinbase symbols: {e}")
        return set()

    coinbase_symbols = {item['base_currency'] for item in products}
    return coinbase_symbols

# =============================================
# FETCH DATA FROM COINMARKETCAP
# =============================================
def fetch_crypto_data():
    headers = {'X-CMC_PRO_API_KEY': API_KEY}
    params = {'start': 1, 'limit': 50, 'convert': 'USD'}
    response = requests.get(BASE_URL, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    if 'data' not in data:
        print("Error: 'data' key not found in API response")
        print(data)
        return None

    return data['data']

def fetch_crypto_metadata():
    headers = {'X-CMC_PRO_API_KEY': API_KEY}
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        return {}

    data = response.json()
    if 'data' not in data or not data['data']:
        print("Error: No metadata found in API response.")
        return {}

    return {item['symbol'].upper(): item['id'] for item in data['data']}

# =============================================
# FETCH TOP 10 CRYPTOS BY MARKET CAP
# =============================================
def fetch_top_10_cryptos():
    headers = {'X-CMC_PRO_API_KEY': API_KEY}
    params = {'start': 1, 'limit': 10, 'convert': 'USD'}
    response = requests.get(BASE_URL, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        print(response.text)
        return []

    data = response.json()
    if 'data' not in data:
        print("Error: 'data' key not found in API response")
        print(data)
        return []

    top_10_cryptos = [
        {
            'rank': idx + 1,
            'name': coin['name'],
            'symbol': coin['symbol'],
            'market_cap': coin['quote']['USD']['market_cap'],
            'price': coin['quote']['USD']['price'],
            'volume': coin['quote']['USD']['volume_24h']
        }
        for idx, coin in enumerate(data['data'])
    ]

    return top_10_cryptos

# =============================================
# CALCULATE RSI (SIMPLIFIED)
# =============================================
def calculate_rsi(prices, window=14):
    deltas = pd.Series(prices).diff(1)
    gain = deltas.where(deltas > 0, 0).rolling(window=window).mean()
    loss = -deltas.where(deltas < 0, 0).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def calculate_certainty(price_change, rsi, volume):
    buy_score = 0
    sell_score = 0

    if rsi < 30:
        buy_score += (30 - rsi) * 2
    elif rsi > 70:
        sell_score += (rsi - 70) * 2

    if price_change < 0:
        buy_score += abs(price_change) * 3
    elif price_change > 0:
        sell_score += price_change * 3

    buy_score += volume * 0.0005
    sell_score += volume * 0.0005

    total_score = buy_score + sell_score
    buy_certainty = (buy_score / total_score) * 100 if total_score > 0 else 0
    sell_certainty = (sell_score / total_score) * 100 if total_score > 0 else 0

    return round(buy_certainty, 2), round(sell_certainty, 2)

# =============================================
# ANALYZE DATA
# =============================================
def analyze_data(data, coinbase_symbols):
    signals = []
    for coin in data:
        symbol = coin['symbol']
        if symbol not in coinbase_symbols:
            continue

        name = coin['name']
        price = coin['quote']['USD']['price']
        volume_24h = coin['quote']['USD']['volume_24h']
        percent_change_24h = coin['quote']['USD'].get('percent_change_24h', 0)

        dummy_prices = [price * (1 - (percent_change_24h / 100))] * 14 + [price]
        rsi = calculate_rsi(dummy_prices)

        buy_certainty, sell_certainty = calculate_certainty(
            percent_change_24h, rsi, volume_24h
        )

        if buy_certainty > sell_certainty:
            signals.append({
                'symbol': symbol,
                'name': name,
                'price': price,
                'rsi': rsi,
                'volume': volume_24h,
                'buy': buy_certainty,
                'sell': sell_certainty
            })

    return signals

def calculate_projected_profit(best_signal, holding_time_days):
    daily_percent_change = best_signal['percent_change_24h'] / 100
    projected_price = best_signal['price'] * ((1 + daily_percent_change) ** holding_time_days)
    initial_investment = 100
    projected_profit = (projected_price - best_signal['price']) * (initial_investment / best_signal['price'])
    return round(projected_profit, 2)

def calculate_holding_time(best_signal):
    percent_change_24h = abs(best_signal['percent_change_24h'])
    if percent_change_24h < 2:
        return 14
    elif percent_change_24h < 5:
        return 7
    else:
        return 2

# =============================================
# MAIN SCRIPT
# =============================================
if __name__ == "__main__":
    print("Fetching list of Coinbase-supported coins...")
    coinbase_symbols = fetch_coinbase_symbols()
    if not coinbase_symbols:
        print("No symbols fetched from Coinbase. Exiting.")
        exit(1)

    print("Fetching top 50 cryptocurrencies from CoinMarketCap...")
    crypto_data = fetch_crypto_data()
    if not crypto_data:
        print("Failed to fetch crypto data. Exiting.")
        exit(1)

    print("Fetching top 10 cryptos by market cap...")
    top_10_cryptos = fetch_top_10_cryptos()

    print("Analyzing data (only for Coinbase-supported coins)...")
    buy_signals = analyze_data(crypto_data, coinbase_symbols)

    print("Fetching cryptocurrency metadata...")
    crypto_metadata = fetch_crypto_metadata()

    for signal in buy_signals:
        signal['coin_id'] = crypto_metadata.get(signal['symbol'], None) or "N/A"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if buy_signals:
        best_signal = max(buy_signals, key=lambda x: x['buy'])
        holding_time_days = calculate_holding_time(best_signal)
        projected_profit = calculate_projected_profit(best_signal, holding_time_days)

        print(f"Best Decision: BUY with {best_signal['buy']}% certainty for {best_signal['symbol']} "
              f"({best_signal['name']}) at ${best_signal['price']:.2f}")
        print(f"Suggested holding time: {holding_time_days} days")
        print(f"Projected profit per $100: ${projected_profit}")
    else:
        best_signal = None
        holding_time_days = None
        projected_profit = None
        print("No strong buy signals found.")

    os.makedirs('scripts', exist_ok=True)
    results = {
        "buy_signals": buy_signals,
        "top_10_cryptos": top_10_cryptos,
        "best_bet": best_signal,
        "suggested_holding_time": holding_time_days,
        "projected_profit_per_100": projected_profit,
        "timestamp": timestamp
    }
    with open("scripts/output.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\nSuccessfully wrote buy signals to scripts/output.json")
