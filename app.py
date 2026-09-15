
import os, json, requests, threading, time
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import yfinance as yf
import pandas as pd

app = Flask(__name__, static_folder='static')
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8752642455:AAEpGTSis6YVij46PrePRZnLqWbQ7OBCZvM")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1033208239")
BUDGET = int(os.getenv("DAILY_BUDGET_SEK", "10000"))
COURTAGE_TYPE = os.getenv("COURTAGE_TYPE", "mini")
MAX_DAILY_LOSS = int(os.getenv("MAX_DAILY_LOSS_SEK", "500"))
DATA_FILE = "/tmp/portfolio_aktieraket_polara.json"
NEWS_CACHE_FILE = "/tmp/news_cache_aktieraket_polara.json"

def calc_courtage(a, t="mini"):
    if t=="mini": return max(1, a*0.0025)
    if t=="small": return max(9, a*0.00055)
    return max(1, a*0.0025)

def load_portfolio():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f: return json.load(f)
    except: pass
    return {"start": BUDGET, "current": BUDGET, "trades": [], "total_pnl": 0.0, "total_pnl_after": 0.0, "total_courtage": 0.0, "win_rate": 0, "win_rate_after": 0, "total": 0, "wins": 0, "wins_after": 0, "daily_pnl": 0.0, "last_reset": datetime.now().date().isoformat()}

def save_portfolio(p):
    try:
        with open(DATA_FILE, "w") as f: json.dump(p, f)
    except: pass

def load_news_cache():
    try:
        if os.path.exists(NEWS_CACHE_FILE):
            with open(NEWS_CACHE_FILE, "r") as f: return json.load(f)
    except: pass
    return []

def save_news_cache(news):
    try:
        with open(NEWS_CACHE_FILE, "w") as f: json.dump(news, f)
    except: pass

portfolio = load_portfolio()
news_cache = load_news_cache()

last_scan = {"time": datetime.now().isoformat(), "raketer": [], "status": "Polara V4 - redo", "portfolio": portfolio, "budget": BUDGET, "max_daily_loss": MAX_DAILY_LOSS, "news": news_cache, "watchlist_prices": []}

WATCHLIST = [
    {"ticker": "SINCH.ST", "name": "Sinch"},
    {"ticker": "EMBRAC-B.ST", "name": "Embracer B"},
    {"ticker": "BOL.ST", "name": "Boliden"},
    {"ticker": "SAAB-B.ST", "name": "Saab B"},
    {"ticker": "VOLV-B.ST", "name": "Volvo B"},
    {"ticker": "INVE-B.ST", "name": "Investor B"},
    {"ticker": "NIBE-B.ST", "name": "Nibe B"},
]

def send_tg(m):
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": m, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_price_data(ticker):
    """Hämtar pris med fallback - fixar '-' problemet"""
    try:
        # Prova flera perioder för svenska aktier
        for period in ["5d", "1mo", "3mo", "6mo"]:
            try:
                df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
                if not df.empty and len(df) > 1:
                    close = df['Close']
                    price = float(close.iloc[-1])
                    prev = float(close.iloc[-2])
                    change = (price - prev) / prev * 100 if prev != 0 else 0
                    # Beräkna volym ratio
                    vol = df['Volume'].iloc[-1] if 'Volume' in df else 0
                    vol_avg = df['Volume'].rolling(20).mean().iloc[-1] if 'Volume' in df and len(df) >= 20 else vol
                    vol_ratio = vol / vol_avg if vol_avg > 0 else 1
                    # RSI snabb
                    delta = close.diff()
                    gain = delta.where(delta>0,0).rolling(14).mean()
                    loss = -delta.where(delta<0,0).rolling(14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1+rs))
                    rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
                    # SMA
                    sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else price
                    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else price
                    return {
                        "price": price,
                        "change": change,
                        "vol_ratio": vol_ratio,
                        "rsi": rsi_val,
                        "sma20": sma20,
                        "sma50": sma50,
                        "df": df
                    }
            except Exception as e:
                print(f"Trying {period} for {ticker} failed: {e}")
                continue
        # Sista fallback - försök info
        try:
            t = yf.Ticker(ticker)
            price = t.info.get('currentPrice') or t.info.get('regularMarketPrice') or 0
            if price > 0:
                return {"price": float(price), "change": 0, "vol_ratio": 1, "rsi": 50, "sma20": price, "sma50": price, "df": None}
        except: pass
        return None
    except Exception as e:
        print(f"get_price_data {ticker} error: {e}")
        return None

def score_fast(data):
    try:
        if not data: return 0, [], {}
        price = data["price"]
        sma20 = data["sma20"]
        sma50 = data["sma50"]
        rsi_val = data["rsi"]
        vol_ratio = data["vol_ratio"]
        s = 0; rsns = []
        if price > sma20: s+=20; rsns.append("Over SMA20")
        if sma20 > sma50: s+=20; rsns.append("SMA20>SMA50")
        if 50 < rsi_val < 70: s+=20; rsns.append(f"RSI {rsi_val:.0f}")
        if vol_ratio > 1.2: s+=20; rsns.append(f"Vol {vol_ratio:.1f}x")
        if data.get("change",0) > 0: s+=10; rsns.append(f"{data['change']:.1f}%")
        if not rsns: rsns.append("Neutral")
        details = {"price": price, "change": data.get("change",0), "rsi": rsi_val, "vol": vol_ratio}
        return max(0,min(100,s)), rsns, details
    except: return 0, [], {}

def fetch_news_fast():
    global news_cache
    try:
        all_news = []
        for item in WATCHLIST[:3]:
            try:
                t = yf.Ticker(item['ticker'])
                raw = t.news
                if not raw: continue
                for n in raw[:2]:
                    title = n.get('title','').strip()
                    if not title or len(title) < 15: continue
                    if any(title == x.get('title') for x in all_news): continue
                    all_news.append({"ticker": item['ticker'], "title": title[:100], "publisher": n.get('publisher',''), "sentiment": "neutral", "time": ""})
                    if len(all_news) >= 6: break
            except: continue
        news_cache = all_news[:8]
        save_news_cache(news_cache)
        last_scan["news"] = news_cache
    except Exception as e:
        print(f"News error {e}")

def job(force=False):
    now = datetime.now()
    # Uppdatera priser för watchlist först - detta fixar "-" i listan
    watchlist_with_prices = []
    rak = []
    for item in WATCHLIST:
        data = get_price_data(item['ticker'])
        if data is None:
            # Om yfinance misslyckas, visa 0 men inte "-"
            watchlist_with_prices.append({**item, "price": 0, "change": 0, "score": 0, "reasons": ["Ingen data just nu - yfinance timeout"], "status": "no_data"})
            continue
        sc, rs, det = score_fast(data)
        watchlist_with_prices.append({**item, "price": data["price"], "change": data.get("change",0), "score": sc, "reasons": rs, "status": "ok", "details": det})
        if sc >= 65:
            rak.append({**item, "score": sc, "price": data["price"], "reasons": rs, "details": det, "change": data.get("change",0)})

    rak.sort(key=lambda x: x["score"], reverse=True)
    last_scan["time"] = now.isoformat()
    last_scan["raketer"] = rak
    last_scan["watchlist_prices"] = watchlist_with_prices
    last_scan["portfolio"] = portfolio
    last_scan["status"] = f"Polara V4 SCAN {len(rak)} raketer - {now.strftime('%H:%M:%S')} - Priser uppdaterade"

    # Spara även om ingen raket - viktigt för att visa priser
    if not force and not (7 <= now.hour < 17):
        last_scan["status"] = f"Vilar {now.strftime('%H:%M')} - {len(rak)} raketer - Priser: {len([w for w in watchlist_with_prices if w['price']>0])}/{len(WATCHLIST)} OK"

    threading.Thread(target=fetch_news_fast, daemon=True).start()
    print(f"Job done: {len(watchlist_with_prices)} prices, {len(rak)} raketer")

# Schedulern
sched = BackgroundScheduler()
sched.add_job(lambda: job(force=False), 'interval', minutes=5)
sched.start()
job(force=True)

@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/manifest.json")
def man(): return send_from_directory('static','manifest.json')
@app.route("/icon-192.png")
def i192(): return send_from_directory('static','icon-192.png')
@app.route("/icon-512.png")
def i512(): return send_from_directory('static','icon-512.png')
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/portfolio")
def pf(): return jsonify(portfolio)
@app.route("/api/news")
def news_api(): return jsonify({"news": last_scan.get("news", news_cache), "time": last_scan.get("time")})
@app.route("/api/courtage")
def ct():
    res=[]
    for a in [1000,2000,5000,10000]:
        c=max(1, a*0.0025)
        res.append({"amount": a, "one_way": c, "both": c*2, "pct": c*2/a*100})
    return jsonify({"type": "mini", "examples": res})
@app.route("/api/test-telegram")
def tt(): 
    send_tg(f"Polara SCAN OK - {len(last_scan.get('watchlist_prices',[]))} priser, {len(last_scan.get('raketer',[]))} raketer")
    return jsonify({"ok": True})
@app.route("/api/scan-now")
def sn(): 
    job(force=True)
    return jsonify(last_scan)
@app.route("/api/reset-daily")
def reset_daily(): 
    portfolio["daily_pnl"]=0.0
    portfolio["last_reset"]=datetime.now().date().isoformat()
    save_portfolio(portfolio)
    return jsonify({"ok": True, "portfolio": portfolio})

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
