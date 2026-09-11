
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
import os, requests, traceback
from datetime import datetime
import yfinance as yf
import pandas as pd

app = Flask(__name__, static_folder='static')

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8752642455:AAEpGTSis6YVij46PrePRZnLqWbQ7OBCZvM")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1033208239")
BUDGET = int(os.getenv("DAILY_BUDGET_SEK", "10000"))

last_scan = {"time": None, "raketer": [], "status": "Startar...", "budget": BUDGET}

WATCHLIST = [
    {"ticker": "SINCH.ST", "name": "Sinch"},
    {"ticker": "EMBRAC-B.ST", "name": "Embracer B"},
    {"ticker": "ALLEI.ST", "name": "Alleima"},
    {"ticker": "BOL.ST", "name": "Boliden"},
    {"ticker": "SAAB-B.ST", "name": "Saab B"},
    {"ticker": "VOLV-B.ST", "name": "Volvo B"},
    {"ticker": "INVE-B.ST", "name": "Investor B"},
    {"ticker": "NIBE-B.ST", "name": "Nibe"},
    {"ticker": "VITR.ST", "name": "Vitrolife"},
    {"ticker": "SBB-B.ST", "name": "SBB B"},
]

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
        print(f"Telegram {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def calculate_simple_score(df):
    try:
        if len(df) < 50:
            return 0, []
        close = df['Close']
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        price = close.iloc[-1]
        reasons = []
        score = 0
        if price > sma20:
            score += 20
            reasons.append("Over SMA20")
        if sma20 > sma50:
            score += 20
            reasons.append("SMA20 > SMA50")
        # RSI simple
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        if 50 < rsi_val < 70:
            score += 20
            reasons.append(f"RSI {rsi_val:.0f}")
        # Volume
        vol = df['Volume'].iloc[-1]
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
        if vol > vol_avg * 1.2:
            score += 20
            reasons.append("Volym okning")
        # Momentum
        if close.iloc[-1] > close.iloc[-5]:
            score += 20
            reasons.append("Momentum +")
        return score, reasons
    except Exception as e:
        print(f"Score error: {e}")
        return 0, []

def get_data(ticker):
    try:
        df = yf.Ticker(ticker).history(period="6mo", interval="1d", auto_adjust=True)
        return None if df.empty else df
    except:
        return None

def trading_job():
    now = datetime.now()
    # Svensk tid 09-11 = UTC 07-09 sommartid
    if not (7 <= now.hour < 11):
        last_scan["status"] = f"Vilar {now.strftime('%H:%M')} UTC - aktiv 07-11 UTC"
        return
    print(f"SCANNING {now}")
    raketer = []
    for item in WATCHLIST:
        df = get_data(item['ticker'])
        if df is None:
            continue
        score, reasons = calculate_simple_score(df)
        if score >= 60:
            raketer.append({**item, "score": score, "price": float(df['Close'].iloc[-1]), "reasons": reasons})
    raketer.sort(key=lambda x: x['score'], reverse=True)
    last_scan["time"] = now.isoformat()
    last_scan["raketer"] = raketer
    last_scan["status"] = f"Hittade {len(raketer)} raketer" if raketer else "Inga raketer >60"
    print(last_scan["status"])
    if raketer:
        msg = f"🚀 *{len(raketer)} raketer {now.strftime('%H:%M')} UTC*\nBudget: {BUDGET}kr\n"
        for r in raketer[:3]:
            msg += f"\n*{r['name']}* {r['score']}/100 @ {r['price']:.1f} SEK\n"
            msg += f"_{', '.join(r['reasons'][:2])}_\n"
        send_telegram(msg)

scheduler = BackgroundScheduler()
scheduler.add_job(trading_job, 'interval', minutes=5)
scheduler.start()
trading_job()

@app.route("/")
def index():
    return send_from_directory('static', 'index.html')

@app.route("/manifest.json")
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route("/icon-192.png")
def icon192():
    return send_from_directory('static', 'icon-192.png')

@app.route("/icon-512.png")
def icon512():
    return send_from_directory('static', 'icon-512.png')

@app.route("/api/status")
def status():
    return jsonify(last_scan)

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "last_scan": last_scan["time"]})

@app.route("/api/test-telegram")
def test_telegram():
    try:
        send_telegram("✅ TEST funkar! Nu med live-scanning 09-11, 500kr budget.")
        return jsonify({"ok": True, "message": "Test skickat! Kolla Telegram."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/scan-now")
def scan_now():
    trading_job()
    return jsonify(last_scan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
