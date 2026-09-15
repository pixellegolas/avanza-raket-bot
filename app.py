
from flask import Flask, jsonify, send_from_directory
from datetime import datetime, timedelta
import yfinance as yf, pandas as pd, json, os, math
from apscheduler.schedulers.background import BackgroundScheduler
import requests

app=Flask(__name__, static_folder='static')
BUDGET=10000
MAX_LOSS=500
CACHE_FILE="/tmp/cache_komplett.json"
PORTFOLIO_FILE="/tmp/portfolio_komplett.json"

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path,"r") as f: return json.load(f)
    except: pass
    return default

def save_json(path, data):
    try:
        with open(path,"w") as f: json.dump(f, data)
    except: pass

portfolio=load_json(PORTFOLIO_FILE, {"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl":0,"total_pnl_after":0,"total_courtage":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0,"last_reset":datetime.now().date().isoformat()})
cache=load_json(CACHE_FILE, {"raketer":[],"watchlist_prices":[],"time":None})

last_scan={
    "budget":BUDGET,"max_daily_loss":MAX_LOSS,"portfolio":portfolio,
    "raketer":cache.get("raketer",[]),"watchlist_prices":cache.get("watchlist_prices",[]),
    "status": f"KOMPLETT POLARA STEG1 ULTRA LIGHT - cache {cache.get('time','aldrig')} - 0 Yahoo vid ping",
    "time": datetime.now().isoformat(),"news":[]
}

WATCHLIST=[
    {"ticker":"SINCH.ST","name":"Sinch","avanza_id":5368},
    {"ticker":"EMBRAC-B.ST","name":"Embracer B","avanza_id":1015165},
    {"ticker":"BOL.ST","name":"Boliden","avanza_id":1570},
    {"ticker":"SAAB-B.ST","name":"Saab B","avanza_id":5411},
    {"ticker":"VOLV-B.ST","name":"Volvo B","avanza_id":853},
    {"ticker":"INVE-B.ST","name":"Investor B","avanza_id":1199},
    {"ticker":"NIBE-B.ST","name":"Nibe B","avanza_id":2605},
]

def safe_float(x, fb=0):
    try:
        if x is None: return fb
        if isinstance(x,float) and (math.isnan(x) or math.isinf(x)): return fb
        if pd.isna(x): return fb
        return float(x)
    except: return fb

def get_avanza_owners(aid):
    try:
        r=requests.get(f"https://www.avanza.se/_mobile/market/stock/{aid}", headers={"User-Agent":"Mozilla/5.0"}, timeout=3)
        if r.status_code==200:
            return int(r.json().get("numberOfOwners",0))
    except: pass
    return 0

def get_data_fixed(ticker):
    for period in ["6mo","1y","3mo"]:
        try:
            t=yf.Ticker(ticker)
            df=t.history(period=period, auto_adjust=True)
            if df.empty or len(df)<20:
                try:
                    info=t.info
                    price=info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                    price=safe_float(price,0)
                    if price>0:
                        return {"price":price,"change":0,"vol_ratio":1,"rsi":50,"sma20":price,"sma50":price,"vwap":price,"price_vs_vwap":0,"atr":price*0.02,"atr_pct":2.0}
                except: pass
                continue
            df=df.dropna()
            if len(df)<20: continue
            close=df['Close']; high=df['High']; low=df['Low']; vol=df['Volume']
            price=safe_float(close.iloc[-1],0)
            if price==0: continue
            prev=safe_float(close.iloc[-2],price) if len(close)>=2 else price
            change=safe_float((price-prev)/prev*100 if prev else 0,0)
            try:
                typical=(high+low+close)/3
                vwap_series=(typical*vol).rolling(20).sum() / vol.rolling(20).sum()
                vwap=safe_float(vwap_series.iloc[-1], price)
            except: vwap=price
            try:
                tr1=high-low; tr2=(high-close.shift(1)).abs(); tr3=(low-close.shift(1)).abs()
                tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
                atr=safe_float(tr.rolling(14).mean().iloc[-1], price*0.02)
            except: atr=price*0.02
            try:
                vol_avg=vol.rolling(20).mean().iloc[-1]
                vol_last=vol.iloc[-1]
                vol_ratio=safe_float(vol_last/vol_avg if vol_avg and vol_avg>0 else 1,1)
            except: vol_ratio=1
            try:
                delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
                rs=gain/loss; rsi=100-(100/(1+rs)); rsi_val=safe_float(rsi.iloc[-1],50)
            except: rsi_val=50
            try:
                sma20=safe_float(close.rolling(20).mean().iloc[-1], price)
                sma50=safe_float(close.rolling(50).mean().iloc[-1], price) if len(close)>=50 else sma20
            except: sma20=price; sma50=price
            return {
                "price":safe_float(price,0),"change":safe_float(change,0),"vol_ratio":safe_float(vol_ratio,1),
                "rsi":safe_float(rsi_val,50),"sma20":safe_float(sma20,price),"sma50":safe_float(sma50,price),
                "vwap":safe_float(vwap,price),"price_vs_vwap":safe_float((price-vwap)/vwap*100 if vwap else 0,0),
                "atr":safe_float(atr,price*0.02),"atr_pct":safe_float(atr/price*100 if price else 2.0,2.0)
            }
        except Exception as e:
            print(f"{ticker} {period} {e}")
            continue
    return None

def kelly_position(score, atr_pct, budget):
    base=budget*0.2
    score_f=max(0.5,min(1.5,(score-30)/40))
    atr_f=max(0.5,min(1.5,2.0/max(0.5,atr_pct)))
    pos=base*score_f*atr_f
    return max(budget*0.1, min(budget*0.35, pos))

def job(force=False):
    global cache
    if not force and cache.get("time"):
        try:
            ct=datetime.fromisoformat(cache["time"])
            if datetime.now()-ct < timedelta(minutes=5):
                last_scan["status"]=f"KOMPLETT CACHE {len(cache.get('raketer',[]))} raketer - {ct.strftime('%H:%M:%S')} - 0 Yahoo (cache 5min) - UptimeRobot ping OK"
                last_scan["raketer"]=cache.get("raketer",[])
                last_scan["watchlist_prices"]=cache.get("watchlist_prices",[])
                last_scan["time"]=datetime.now().isoformat()
                print(last_scan["status"])
                return
        except: pass
    now=datetime.now()
    watch=[]; rak=[]
    print(f"FRESH SCAN 7 Yahoo at {now}")
    for item in WATCHLIST:
        d=get_data_fixed(item["ticker"])
        owners=get_avanza_owners(item["avanza_id"]) if force else 0
        if not d or d["price"]==0:
            watch.append({**item,"price":0,"change":0,"score":0,"reasons":["Ingen data"],"vwap":0,"atr":0,"atr_pct":0,"position_size":1000,"owners":owners})
            continue
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
        score=min(100,s)
        pos=kelly_position(score, d["atr_pct"], BUDGET)
        watch.append({**item,"price":d["price"],"change":d["change"],"score":score,"reasons":rs,"vwap":d["vwap"],"price_vs_vwap":d["price_vs_vwap"],"atr":d["atr"],"atr_pct":d["atr_pct"],"position_size":pos,"owners":owners,"rsi":d["rsi"]})
        if score>=50:
            stop=d["price"]-d["atr"]*1.5
            take=d["price"]+d["atr"]*2.5
            rak.append({**item,"score":score,"price":d["price"],"reasons":rs,"change":d["change"],"vwap":d["vwap"],"atr":d["atr"],"stop_loss":stop,"take_profit":take,"position_size":pos,"owners":owners})
    rak.sort(key=lambda x:x["score"], reverse=True)
    last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch; last_scan["portfolio"]=portfolio
    last_scan["status"]=f"KOMPLETT FULL POLARA STEG1 ULTRA LIGHT {len(rak)} raketer - {now.strftime('%H:%M:%S')} - 7 Yahoo OK - safe_float - VWAP+ATR+Kelly"
    cache={"raketer":rak,"watchlist_prices":watch,"time":now.isoformat()}
    save_json(CACHE_FILE, cache)
    save_json(PORTFOLIO_FILE, portfolio)
    print(last_scan["status"])

sched=BackgroundScheduler()
sched.add_job(lambda: job(force=False), 'interval', minutes=10)
sched.start()
job(force=True)

@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/ping")
def ping(): return jsonify({"ok":True,"time":datetime.now().strftime('%H:%M:%S'),"yahoo_calls":0,"message":"Ultra light ping - 0 Yahoo - för UptimeRobot gratis"})
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/scan-now")
def sn(): job(force=True); return jsonify(last_scan)
@app.route("/api/portfolio")
def pf(): return jsonify(portfolio)

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
