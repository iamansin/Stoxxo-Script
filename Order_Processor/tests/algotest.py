import requests
import datetime

TRADE_SIGNAL_URL = "https://orders.algotest.in/webhook/tv/tk-trade?token=US8CD3R2JSpWWvRGbfwcYCgHRb8w8BFh&tag=68eb4e7474d39905b8d6e20c"

def nowstr():
    return datetime.datetime.now().strftime("%H:%M:%S")

def send_plain_trade_signal(instrument, action="sell", lots=1):
    """Send a plain text trade signal to the webhook."""
    headers = {"Content-Type": "text/plain"}
    payload = f"{instrument} {action} {lots}"

    try:
        resp = requests.post(TRADE_SIGNAL_URL, data=payload, headers=headers, timeout=10)
        print(f"[{nowstr()}] 🔹 Sent payload: {repr(payload)}")
        print(f"the response is : {resp}")
        print(f"→ Status Code: {resp.status_code}")
        print(f"→ Response: {resp.text}")
    except Exception as e:
        print(f"[{nowstr()}] ❌ Error sending payload: {e}")

# Example usage
if __name__ == "__main__":
    instrument = "NIFTY251014P25400"
    send_plain_trade_signal(instrument, action="SELL", lots=1)
