
import os, json
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import yfinance as yf
import pandas as pd

app = Flask(__name__, static_folder='static')
BUDGET=10000
MAX_LOSS=500
portfolio={"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl":0,"total_pnl_after":0,"total_courtage":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0}
last_scan={"budget":BUDGET,"max_daily_loss":MAX_LOSS,"portfolio":portfolio,"raketer":[],"watchlist_prices":[],"status":"Init","time":datetime.now().isoformat(),"news":[]}
WATCHLIST=[{"ticker":"SINCH.ST","name":"Sinch"},{"ticker":"EMBRAC-B.ST","name":"Embracer B"},{"ticker":"BOL.ST","name":"Boliden"},{"ticker":"SAAB-B.ST","name":"Saab B"},{"ticker":"VOLV-B.ST","name":"Volvo B"},{"ticker":"INVE-B.ST","name":"Investor B"},{"ticker":"NIBE-B.ST","name":"Nibe B"}]

def get_data(t):
    try:
        for period in ["6mo","3mo","1mo","5d"]:
            df=yf.Ticker(t).history(period=period, auto_adjust=True)
            if df.empty or len(df)<10: continue
            close=df['Close']; price=float(close.iloc[-1]); prev=float(close.iloc[-2]) if len(close)>=2 else price
            change=(price-prev)/prev*100 if prev else 0
            vol=df['Volume'].iloc[-1] if 'Volume' in df else 0
            vol_avg=df['Volume'].rolling(20).mean().iloc[-1] if len(df)>=20 else vol
            vol_ratio=vol/vol_avg if vol_avg else 1
            delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
            rs=gain/loss; rsi=100-(100/(1+rs)); rsi_val=float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
            sma20=close.rolling(20).mean().iloc[-1] if len(close)>=20 else close.mean()
            sma50=close.rolling(50).mean().iloc[-1] if len(close)>=50 else close.mean()
            return {"price":price,"change":change,"vol_ratio":float(vol_ratio),"rsi":float(rsi_val),"sma20":float(sma20),"sma50":float(sma50),"df":df}
    except: pass
    return None

def score(d):
    if not d: return 0,["Ingen data"],{}
    s=0; r=[]
    if d["price"]>d["sma20"]: s+=25; r.append("Over SMA20")
    elif d["price"]>d["sma20"]*0.98: s+=10; r.append("Nära SMA20")
    if d["sma20"]>d["sma50"]: s+=25; r.append("SMA20>SMA50")
    if 30<d["rsi"]<70: s+=20; r.append(f"RSI {d['rsi']:.0f}")
    if d["vol_ratio"]>1: s+=15; r.append(f"Vol {d['vol_ratio']:.1f}x")
    if d["change"]>0: s+=10; r.append(f"{d['change']:+.1f}%")
    if s==0: s=20; r=["Neutral"]
    return min(100,s), r, {"price":d["price"],"change":d["change"]}

def job(force=False):
    now=datetime.now(); watch=[]; rak=[]
    for item in WATCHLIST:
        d=get_data(item["ticker"])
        if not d: watch.append({**item,"price":0,"change":0,"score":0,"reasons":["Ingen data"],"status":"no_data"}); continue
        sc,rs,det=score(d)
        watch.append({**item,"price":d["price"],"change":d["change"],"score":sc,"reasons":rs,"status":"ok","rsi":d["rsi"]})
        if sc>=50: rak.append({**item,"score":sc,"price":d["price"],"reasons":rs,"change":d["change"]})
    rak.sort(key=lambda x:x["score"], reverse=True)
    last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch
    last_scan["status"]=f"FINAL {len(rak)} raketer - {now.strftime('%H:%M:%S')} - {len([w for w in watch if w['price']>0])}/{len(WATCHLIST)} priser OK"

sched=BackgroundScheduler(); sched.add_job(lambda: job(force=False), 'interval', minutes=5); sched.start(); job(force=True)

@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/scan-now")
def sn(): job(force=True); return jsonify(last_scan)
@app.route("/api/test-telegram")
def tt(): return jsonify({"ok":True})

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
