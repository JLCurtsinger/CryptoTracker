from datetime import datetime
import json
import requests
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

    # Extract base_currency from each product (e.g., 'BTC' in 'BTC-USD')
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

# =============================================
# CALCULATE BUY/SELL CERTAINTY
# =============================================
# def calculate_certainty(price_change, rsi, volume):
#     # Example weights for buy/sell calculation
#     buy_score = 0
#     sell_score = 0

#     # RSI contribution (lower RSI favors buy)
#     if rsi < 30:
#         buy_score += (30 - rsi) * 1.5  # Oversold zone
#     elif rsi > 70:
#         sell_score += (rsi - 70) * 1.5  # Overbought zone

#     # Price change contribution
#     if price_change < 0:
#         buy_score += abs(price_change) * 2  # Favor negative price changes for buy
#     elif price_change > 0:
#         sell_score += price_change * 2      # Favor positive price changes for sell

#     # Volume contribution (higher volume increases confidence for both)
#     buy_score += volume * 0.001
#     sell_score += volume * 0.001

#     # Normalize scores to 0-100%
#     total_score = buy_score + sell_score
#     buy_certainty = (buy_score / total_score) * 100 if total_score > 0 else 0
#     sell_certainty = (sell_score / total_score) * 100 if total_score > 0 else 0

#     return round(buy_certainty, 2), round(sell_certainty, 2)

def calculate_certainty(price_change, rsi, volume):
    buy_score = 0
    sell_score = 0

    # Give more weight to RSI influence
    if rsi < 30:
        buy_score += (30 - rsi) * 2  # Increase multiplier for oversold
    elif rsi > 70:
        sell_score += (rsi - 70) * 2  # Increase multiplier for overbought

    # Emphasize price changes over volume
    if price_change < 0:
        buy_score += abs(price_change) * 3  # Heavily favor negative price changes
    elif price_change > 0:
        sell_score += price_change * 3  # Heavily favor positive price changes

    # Reduce volume influence
    buy_score += volume * 0.0005  # Half the previous weight
    sell_score += volume * 0.0005

    total_score = buy_score + sell_score
    buy_certainty = (buy_score / total_score) * 100 if total_score > 0 else 0
    sell_certainty = (sell_score / total_score) * 100 if total_score > 0 else 0

    return round(buy_certainty, 2), round(sell_certainty, 2)

# =============================================
# ANALYZE DATA (FILTER FOR COINBASE SYMBOLS)
# =============================================
def analyze_data(data, coinbase_symbols):
    """
    data: list of coin data from CoinMarketCap
    coinbase_symbols: set of symbols (e.g., {'BTC','ETH'}) tradable on Coinbase
    """
    signals = []
    for coin in data:
        symbol = coin['symbol']

        # FILTER: Only analyze if the symbol is supported by Coinbase
        if symbol not in coinbase_symbols:
            continue

        name = coin['name']
        price = coin['quote']['USD']['price']
        volume_24h = coin['quote']['USD']['volume_24h']
        percent_change_24h = coin['quote']['USD']['percent_change_24h']

        # Simplified RSI calculation using dummy historical prices
        dummy_prices = [price * (1 - (percent_change_24h / 100))] * 14 + [price]
        rsi = calculate_rsi(dummy_prices)

        # Calculate buy/sell certainty
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

# Calculate projected profit per $100 investment
def calculate_projected_profit(best_signal, holding_time_days):
    # Assume the price change (percent_change_24h) continues over the holding time
    daily_percent_change = best_signal['price'] * (best_signal['buy'] / 100)
    projected_price = best_signal['price'] * ((1 + (daily_percent_change / 100)) ** holding_time_days)

    # Calculate profit per $100
    initial_investment = 100
    projected_profit = (projected_price - best_signal['price']) * (initial_investment / best_signal['price'])
    return round(projected_profit, 2)

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

    # DISPLAY RESULTS to console
    if buy_signals:
        print("\nPotential Buy Signals (Coinbase-Only):")
        print(f"{'Coin':<10} {'Price ($)':<10} {'RSI':<6} {'Volume ($)':<15}")
        print("-" * 45)
        for signal in buy_signals:
            print(f"{signal['symbol']:<10} {signal['price']:<10.2f} {signal['rsi']:<6.2f} {signal['volume']:<15.2f}")

        print("\nBuy/Sell Certainty Scores:")
        print(f"{'Coin':<10} {'Price ($)':<10} {'Buy (%)':<10} {'Sell (%)':<10}")
        print("-" * 45)
        for signal in buy_signals:
            print(f"{signal['symbol']:<10} {signal['price']:<10.2f} {signal['buy']:<10.2f} {signal['sell']:<10.2f}")

        # best_signal = max(buy_signals, key=lambda x: max(x['buy'], x['sell']))
         # Identify the coin with the highest buy chance
        best_signal = max(buy_signals, key=lambda x: x['buy']) if buy_signals else None
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        decision = "BUY" if best_signal['buy'] > best_signal['sell'] else "SELL"
        certainty = max(best_signal['buy'], best_signal['sell'])
        print(f"\nBest Decision: {decision} {certainty}% for {best_signal['symbol']} "
              f"({best_signal['name']}) at ${best_signal['price']:.2f}")
    else:
        print("No buy signals found among Coinbase-supported coins.")

    # SAVE RESULTS TO A JSON FILE
    # -------------------------------------------------
    # JSON Output
    holding_time_days = 30  # Example holding period in days
    projected_profit = calculate_projected_profit(best_signal, holding_time_days)
    
    results = {
        "buy_signals": buy_signals,
        "top_10_cryptos": top_10_cryptos,
        "best_bet": best_signal,
        "suggested_holding_time": holding_time_days,
        "projected_profit_per_100": projected_profit,
        "timestamp": timestamp
    }
    # This creates/overwrites 'scripts/output.json' with the final signals
    with open("scripts/output.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSuccessfully wrote buy signals to scripts/output.json")
