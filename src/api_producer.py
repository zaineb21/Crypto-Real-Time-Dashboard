# api_producer.py
import json
import time
import requests
from datetime import datetime
from kafka import KafkaProducer

# ─── Configuration ───────────────────────────────────────────────────────────
KAFKA_BROKER = "localhost:9092"
TOPIC        = "crypto-topic"
POLL_INTERVAL = 5  # seconds between API calls

# Fetch both BTC and ETH
SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# ─── Kafka Producer ──────────────────────────────────────────────────────────
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=3  # retry on transient errors
)

def fetch_price(symbol: str) -> dict | None:
    """Fetch latest price for a symbol from Binance REST API."""
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        return {
            "symbol":     data["symbol"],
            "price":      float(data["price"]),
            "event_time": datetime.utcnow().isoformat()
        }

    except requests.exceptions.HTTPError as e:
        print(f"[HTTP ERROR] {symbol}: {e}")
    except requests.exceptions.ConnectionError:
        print(f"[CONNECTION ERROR] {symbol}: cannot reach Binance API")
    except requests.exceptions.Timeout:
        print(f"[TIMEOUT] {symbol}: request took too long")
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")

    return None


def main():
    print(f"🚀 Starting API Producer — symbols: {SYMBOLS}")
    print(f"   Kafka broker : {KAFKA_BROKER}")
    print(f"   Topic        : {TOPIC}")
    print(f"   Poll interval: {POLL_INTERVAL}s\n")

    while True:
        for symbol in SYMBOLS:
            event = fetch_price(symbol)
            if event:
                producer.send(TOPIC, value=event, key=symbol.encode("utf-8"))
                print(f"[SENT] {event}")

        producer.flush()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()