
import os, json, re
from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import yfinance as yf
import pandas as pd
import requests

app = Flask(__name__, static_folder='static')
BUDGET=10000
MAX_LOSS=500
DATA_FILE="/tmp/portfolio_full_steg1.json"
def load_portfolio():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE,"r") as f: return json.load(f)
    except: pass
    return {"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl":0,"total_pnl_after":0,"total_courtage":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0,"last_reset":datetime.now().date().isoformat()}
def save_portfolio(p):
    try:
        with open(DATA_FILE,"w") as f: json.dump(p,f)
    except: pass

portfolio=load_portfolio()
last_scan={"budget":BUDGET,"max_daily_loss":MAX_LOSS,"portfolio":portfolio,"raketer":[],"watchlist_prices":[],"status":"FULL POLARA STEG1 Init","time":datetime.now().isoformat(),"news":[]}
WATCHLIST=[{"ticker":"SINCH.ST","name":"Sinch","avanza_id":5368},{"ticker":"EMBRAC-B.ST","name":"Embracer B","avanza_id":1015165},{"ticker":"BOL.ST","name":"Boliden","avanza_id":1570},{"ticker":"SAAB-B.ST","name":"Saab B","avanza_id":5411},{"ticker":"VOLV-B.ST","name":"Volvo B","avanza_id":853},{"ticker":"INVE-B.ST","name":"Investor B","avanza_id":1199},{"ticker":"NIBE-B.ST","name":"Nibe B","avanza_id":2605}]

def get_avanza_owners(aid):
    try:
        url=f"https://www.avanza.se/_mobile/market/stock/{aid}"
        r=requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=4)
        if r.status_code==200:
            j=r.json()
            return int(j.get("numberOfOwners",0))
    except Exception as e:
        print(f"Avanza {aid} err {e}")
    return 0

def get_data(t):
    try:
        for period in ["6mo","3mo"]:
            df=yf.Ticker(t).history(period=period, auto_adjust=True)
            if df.empty or len(df)<30: continue
            close=df['Close']; high=df['High']; low=df['Low']; vol=df['Volume']
            price=float(close.iloc[-1]); prev=float(close.iloc[-2]) if len(close)>=2 else price
            change=(price-prev)/prev*100 if prev else 0
            typical=(high+low+close)/3
            vwap=float((typical*vol).rolling(20).sum().iloc[-1] / vol.rolling(20).sum().iloc[-1]) if len(df)>=20 else price
            tr1=high-low; tr2=(high-close.shift(1)).abs(); tr3=(low-close.shift(1)).abs()
            tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
            atr=float(tr.rolling(14).mean().iloc[-1]) if len(df)>=14 else price*0.02
            vol_avg=float(vol.rolling(20).mean().iloc[-1]) if len(df)>=20 else float(vol.iloc[-1])
            vol_ratio=float(vol.iloc[-1]/vol_avg) if vol_avg else 1
            delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
            rs=gain/loss; rsi=100-(100/(1+rs)); rsi_val=float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
            sma20=float(close.rolling(20).mean().iloc[-1]); sma50=float(close.rolling(50).mean().iloc[-1]) if len(close)>=50 else sma20
            return {"price":price,"change":change,"vol_ratio":vol_ratio,"rsi":rsi_val,"sma20":sma20,"sma50":sma50,"vwap":vwap,"price_vs_vwap":(price-vwap)/vwap*100,"atr":atr,"atr_pct":atr/price*100}
    except Exception as e:
        print(f"get_data {t} err {e}")
    return None

def kelly_position(score, atr_pct, budget):
    base=budget*0.2
    score_f=max(0.5,min(1.5,(score-30)/40))
    atr_f=max(0.5,min(1.5,2.0/max(0.5,atr_pct)))
    pos=base*score_f*atr_f
    return max(budget*0.1, min(budget*0.35, pos))

def score_steg1(d, owners):
    if not d: return 0,["Ingen data"],{}
    s=0; rs=[]
    if d["price"]>d["sma20"]: s+=20; rs.append("Over SMA20")
    elif d["price"]>d["sma20"]*0.98: s+=8; rs.append("Nära SMA20")
    if d["sma20"]>d["sma50"]: s+=20; rs.append("SMA20>SMA50")
    if d["price"]>d["vwap"]: s+=20; rs.append(f"Over VWAP {d['price_vs_vwap']:+.1f}%")
    elif d["price_vs_vwap"]>-0.5: s+=5; rs.append(f"Nära VWAP {d['price_vs_vwap']:+.1f}%")
    if 30<d["rsi"]<70: s+=15; rs.append(f"RSI {d['rsi']:.0f}")
    if d["vol_ratio"]>1: s+=10; rs.append(f"Vol {d['vol_ratio']:.1f}x")
    if d["change"]>0: s+=10; rs.append(f"{d['change']:+.1f}%")
    if owners>0: s+=5; rs.append(f"{owners//1000}k ägare")
    rs.append(f"ATR {d['atr_pct']:.1f}%")
    if s==0: s=20; rs=["Neutral"]
    return min(100,s), rs, d

def job(force=False):
    now=datetime.now(); watch=[]; rak=[]
    for item in WATCHLIST:
        d=get_data(item["ticker"])
        owners=get_avanza_owners(item["avanza_id"])
        if not d:
            watch.append({**item,"price":0,"change":0,"score":0,"reasons":["Ingen data"],"owners":owners,"status":"no_data"})
            continue
        sc,rs,det=score_steg1(d, owners)
        pos=kelly_position(sc, d["atr_pct"], BUDGET)
        watch.append({**item,"price":d["price"],"change":d["change"],"score":sc,"reasons":rs,"owners":owners,"vwap":d["vwap"],"price_vs_vwap":d["price_vs_vwap"],"atr":d["atr"],"atr_pct":d["atr_pct"],"position_size":pos,"rsi":d["rsi"],"status":"ok"})
        if sc>=50:
            stop=d["price"]-d["atr"]*1.5
            take=d["price"]+d["atr"]*2.5
            rak.append({**item,"score":sc,"price":d["price"],"reasons":rs,"change":d["change"],"vwap":d["vwap"],"atr":d["atr"],"stop_loss":stop,"take_profit":take,"position_size":pos,"owners":owners})
    rak.sort(key=lambda x:x["score"], reverse=True)
    last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch; last_scan["portfolio"]=portfolio
    last_scan["status"]=f"FULL POLARA STEG1 {len(rak)} raketer - {now.strftime('%H:%M:%S')} - {len([w for w in watch if w['price']>0])}/{len(WATCHLIST)} priser OK - VWAP+ATR+Kelly"
    print(last_scan["status"])

sched=BackgroundScheduler(); sched.add_job(lambda: job(force=False), 'interval', minutes=5); sched.start(); job(force=True)

@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/portfolio")
def pf(): return jsonify(portfolio)
@app.route("/api/scan-now")
def sn(): job(force=True); return jsonify(last_scan)
@app.route("/api/test-telegram")
def tt(): return jsonify({"ok":True})

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
