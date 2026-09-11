
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
import os, requests
from datetime import datetime
import yfinance as yf

app = Flask(__name__, static_folder='static')
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8752642455:AAEpGTSis6YVij46PrePRZnLqWbQ7OBCZvM")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1033208239")
BUDGET = int(os.getenv("DAILY_BUDGET_SEK", "500"))

portfolio = {"start": BUDGET, "current": BUDGET, "trades": [], "total_pnl": 0.0, "win_rate": 0, "total": 0, "wins": 0}
last_scan = {"time": None, "raketer": [], "status": "DEMO startar...", "portfolio": portfolio, "budget": BUDGET}

WATCHLIST = [{"ticker": "SINCH.ST", "name": "Sinch"},{"ticker": "EMBRAC-B.ST", "name": "Embracer B"},{"ticker": "ALLEI.ST", "name": "Alleima"},{"ticker": "BOL.ST", "name": "Boliden"},{"ticker": "SAAB-B.ST", "name": "Saab B"},{"ticker": "VOLV-B.ST", "name": "Volvo B"},{"ticker": "INVE-B.ST", "name": "Investor B"},{"ticker": "NIBE-B.ST", "name": "Nibe"},{"ticker": "VITR.ST", "name": "Vitrolife"},{"ticker": "SBB-B.ST", "name": "SBB B"}]

def send_tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": m, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def score(df):
    try:
        if len(df)<50: return 0,[]
        c=df['Close']; sma20=c.rolling(20).mean().iloc[-1]; sma50=c.rolling(50).mean().iloc[-1]; p=c.iloc[-1]; r=[]; s=0
        if p>sma20: s+=20; r.append("Over SMA20")
        if sma20>sma50: s+=20; r.append("SMA20>SMA50")
        d=c.diff(); g=d.where(d>0,0).rolling(14).mean(); l=-d.where(d<0,0).rolling(14).mean(); rs=g/l; rsi=100-(100/(1+rs)); rv=rsi.iloc[-1]
        if 50<rv<70: s+=20; r.append(f"RSI {rv:.0f}")
        v=df['Volume'].iloc[-1]; va=df['Volume'].rolling(20).mean().iloc[-1]
        if v>va*1.2: s+=20; r.append("Volym+")
        if c.iloc[-1]>c.iloc[-5]: s+=20; r.append("Momentum+")
        return s,r
    except: return 0,[]

def getd(t):
    try:
        df=yf.Ticker(t).history(period="6mo", auto_adjust=True)
        return None if df.empty else df
    except: return None

def job():
    now=datetime.now()
    if not (7<=now.hour<11):
        last_scan["status"]=f"DEMO vilar {now.strftime('%H:%M')} UTC - aktiv 09-11 svensk tid"; last_scan["portfolio"]=portfolio; return
    rak=[]
    for it in WATCHLIST:
        df=getd(it["ticker"])
        if df is None: continue
        sc, rs=score(df)
        if sc>=60:
            rak.append({**it, "score": sc, "price": float(df['Close'].iloc[-1]), "reasons": rs})
            if portfolio["current"]>=BUDGET*0.2 and not any(tr["ticker"]==it["ticker"] and tr.get("sell_price") is None for tr in portfolio["trades"]):
                tr={"ticker":it["ticker"],"name":it["name"],"buy_price":float(df['Close'].iloc[-1]),"buy_time":now.isoformat(),"score":sc,"sell_price":None,"pnl":0}
                portfolio["trades"].append(tr); portfolio["current"]-=BUDGET*0.2
    for tr in portfolio["trades"]:
        if tr["sell_price"] is None:
            df=getd(tr["ticker"])
            if df is None: continue
            cp=float(df['Close'].iloc[-1]); pct=(cp-tr["buy_price"])/tr["buy_price"]
            days=(now-datetime.fromisoformat(tr["buy_time"])).days
            if pct>=0.03 or pct<=-0.02 or days>=3:
                tr["sell_price"]=cp; tr["sell_time"]=now.isoformat(); tr["pnl"]=(cp-tr["buy_price"])*(BUDGET*0.2/tr["buy_price"]); tr["pnl_pct"]=pct*100
                portfolio["total_pnl"]+=tr["pnl"]; portfolio["total"]+=1
                if tr["pnl"]>0: portfolio["wins"]+=1
                if portfolio["total"]>0: portfolio["win_rate"]=portfolio["wins"]/portfolio["total"]*100
                portfolio["current"]+=BUDGET*0.2+tr["pnl"]
    rak.sort(key=lambda x:x["score"], reverse=True)
    last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak
    last_scan["status"]=f"DEMO {len(rak)} raketer | P/L {portfolio['total_pnl']:.1f}kr | WinRate {portfolio['win_rate']:.0f}% | Trades {portfolio['total']}"
    last_scan["portfolio"]=portfolio
    if rak:
        msg=f"🚀 *DEMO {len(rak)} raketer {now.strftime('%H:%M')}*\nBudget 500kr (låtsas)\nP/L: {portfolio['total_pnl']:.1f}kr WinRate: {portfolio['win_rate']:.0f}% Trades: {portfolio['total']}\n"
        for r in rak[:3]: msg+=f"\n*{r['name']}* {r['score']}/100 @ {r['price']:.1f} SEK"
        send_tg(msg)

sched=BackgroundScheduler(); sched.add_job(job, 'interval', minutes=5); sched.start(); job()

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
@app.route("/api/test-telegram")
def tt(): send_tg(f"✅ DEMO-LÄGE\nBudget 500kr låtsas\nP/L {portfolio['total_pnl']:.1f}kr\nWinRate {portfolio['win_rate']:.0f}%\nTrades {portfolio['total']}\n\nInga riktiga köp - bara test av effektivitet."); return jsonify({"ok":True,"message":f"P/L {portfolio['total_pnl']:.1f}kr"})
@app.route("/api/scan-now")
def sn(): job(); return jsonify(last_scan)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
