
from flask import Flask, jsonify, send_from_directory
from datetime import datetime
import yfinance as yf, pandas as pd, requests, os, json
from apscheduler.schedulers.background import BackgroundScheduler
app=Flask(__name__, static_folder='static')
BUDGET=10000
portfolio={"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl_after":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0}
cache={"raketer":[],"watchlist_prices":[],"cache_time":None}
last_scan={"budget":BUDGET,"max_daily_loss":500,"portfolio":portfolio,"raketer":[],"watchlist_prices":[],"status":"ULTRA LIGHT Init","time":datetime.now().isoformat()}
WATCHLIST=[{"ticker":"SINCH.ST","name":"Sinch","avanza_id":5368},{"ticker":"EMBRAC-B.ST","name":"Embracer B","avanza_id":1015165},{"ticker":"BOL.ST","name":"Boliden","avanza_id":1570},{"ticker":"SAAB-B.ST","name":"Saab B","avanza_id":5411},{"ticker":"VOLV-B.ST","name":"Volvo B","avanza_id":853},{"ticker":"INVE-B.ST","name":"Investor B","avanza_id":1199},{"ticker":"NIBE-B.ST","name":"Nibe B","avanza_id":2605}]
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
 except: pass
 return None
def kelly(score, atr_pct):
 base=BUDGET*0.2
 sf=max(0.5,min(1.5,(score-30)/40))
 af=max(0.5,min(1.5,2.0/max(0.5,atr_pct)))
 pos=base*sf*af
 return max(BUDGET*0.1, min(BUDGET*0.35, pos))
def job(force=False):
 now=datetime.now(); watch=[]; rak=[]
 for item in WATCHLIST:
  d=get_data(item["ticker"])
  if not d: watch.append({**item,"price":0,"score":0}); continue
  s=0; rs=[]
  if d["price"]>d["sma20"]: s+=20; rs.append("Over SMA20")
  if d["sma20"]>d["sma50"]: s+=20; rs.append("SMA20>SMA50")
  if d["price"]>d["vwap"]: s+=20; rs.append(f"VWAP {d['price_vs_vwap']:+.1f}%")
  if 30<d["rsi"]<70: s+=15; rs.append(f"RSI {d['rsi']:.0f}")
  if d["vol_ratio"]>1: s+=10; rs.append(f"Vol {d['vol_ratio']:.1f}x")
  if d["change"]>0: s+=10; rs.append(f"{d['change']:+.1f}%")
  rs.append(f"ATR {d['atr_pct']:.1f}%")
  sc=min(100,s) if s else 20
  pos=kelly(sc, d["atr_pct"])
  watch.append({**item,"price":d["price"],"change":d["change"],"score":sc,"reasons":rs,"vwap":d["vwap"],"atr":d["atr"],"atr_pct":d["atr_pct"],"position_size":pos})
  if sc>=50:
   stop=d["price"]-d["atr"]*1.5
   rak.append({**item,"score":sc,"price":d["price"],"reasons":rs,"change":d["change"],"vwap":d["vwap"],"stop_loss":stop,"position_size":pos})
 rak.sort(key=lambda x:x["score"], reverse=True)
 last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch
 last_scan["status"]=f"ULTRA LIGHT {len(rak)} raketer - {now.strftime('%H:%M:%S')} - Cache 5min"

sched=BackgroundScheduler(); sched.add_job(lambda: job(force=False), 'interval', minutes=10); sched.start(); job(force=True)

@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/ping")
def ping(): return jsonify({"ok":True,"time":datetime.now().strftime('%H:%M:%S'),"yahoo_calls":0,"message":"Lätt ping - 0 Yahoo"})
@app.route("/api/status")
def status(): return jsonify(last_scan)
@app.route("/api/scan-now")
def scan_now(): job(force=True); return jsonify(last_scan)

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
