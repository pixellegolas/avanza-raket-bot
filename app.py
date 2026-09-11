
import os
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf
from strategy import calculate_rocket_score
from telegram_notifier import TelegramNotifier
from datetime import datetime

app = Flask(__name__, static_folder='static')
notifier = TelegramNotifier()
last_scan = {"time": None, "raketer": [], "status": "Startar..."}

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

def get_live_data(ticker):
    try:
        df = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
        return None if df.empty else df
    except:
        return None

def trading_job():
    now = datetime.now()
    if not (7 <= now.hour < 11):
        last_scan["status"] = f"Vilar {now.strftime('%H:%M')} UTC"
        return
    raketer = []
    for item in WATCHLIST:
        df = get_live_data(item['ticker'])
        if df is None:
            continue
        score, reasons = calculate_rocket_score(df)
        if score >= 70:
            raketer.append({**item, "score": score, "price": float(df['Close'].iloc[-1]), "reasons": reasons})
    last_scan["time"] = now.isoformat()
    last_scan["raketer"] = sorted(raketer, key=lambda x: x['score'], reverse=True)
    last_scan["status"] = f"Hittade {len(raketer)} raketer" if raketer else "Inga raketer >70"
    if raketer:
        msg = f"🚀 {len(raketer)} raketer\n" + "\n".join([f"{r['name']} {r['score']}/100 @ {r['price']:.1f}" for r in raketer[:3]])
        notifier.send(msg)

scheduler = BackgroundScheduler()
scheduler.add_job(trading_job, 'interval', minutes=2)
scheduler.start()
trading_job()

@app.route("/")
def dashboard():
    return send_from_directory('static', 'index.html')

@app.route("/api/status")
def status():
    return jsonify(last_scan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
