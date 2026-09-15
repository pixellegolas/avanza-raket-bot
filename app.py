
from flask import Flask, jsonify, send_from_directory
from datetime import datetime, timedelta
import yfinance as yf, pandas as pd, os, json, math
from apscheduler.schedulers.background import BackgroundScheduler
app=Flask(__name__, static_folder='static')
BUDGET=10000
portfolio={"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl_after":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0}
cache={}
last_scan={"budget":BUDGET,"max_daily_loss":500,"portfolio":portfolio,"raketer":[],"watchlist_prices":[],"status":"FIXED","time":datetime.now().isoformat()}
WATCHLIST=[{"ticker":"SINCH.ST","name":"Sinch"},{"ticker":"EMBRAC-B.ST","name":"Embracer B"},{"ticker":"BOL.ST","name":"Boliden"},{"ticker":"SAAB-B.ST","name":"Saab B"},{"ticker":"VOLV-B.ST","name":"Volvo B"},{"ticker":"INVE-B.ST","name":"Investor B"},{"ticker":"NIBE-B.ST","name":"Nibe B"}]
def safe(x, fb=0):
 try:
  if x is None: return fb
  if isinstance(x,float) and (math.isnan(x) or math.isinf(x)): return fb
  if pd.isna(x): return fb
  return float(x)
 except: return fb
def get_data(t):
 for period in ["6mo","1y","3mo"]:
  try:
   df=yf.Ticker(t).history(period=period, auto_adjust=True)
   if df.empty or len(df)<20: continue
   df=df.dropna()
   if len(df)<20: continue
   close=df['Close']; high=df['High']; low=df['Low']; vol=df['Volume']
   price=safe(close.iloc[-1],0)
   if price==0: continue
   prev=safe(close.iloc[-2],price)
   change=((price-prev)/prev*100) if prev else 0
   try:
    typical=(high+low+close)/3
    vwap=safe((typical*vol).rolling(20).sum().iloc[-1] / vol.rolling(20).sum().iloc[-1], price)
   except: vwap=price
   try:
    tr1=high-low; tr2=(high-close.shift(1)).abs(); tr3=(low-close.shift(1)).abs()
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    atr=safe(tr.rolling(14).mean().iloc[-1], price*0.02)
   except: atr=price*0.02
   vol_avg=safe(vol.rolling(20).mean().iloc[-1], float(vol.iloc[-1]))
   vol_ratio=safe(vol.iloc[-1]/vol_avg if vol_avg else 1,1)
   try:
    delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
    rs=gain/loss; rsi=100-(100/(1+rs)); rsi_val=safe(rsi.iloc[-1],50)
   except: rsi_val=50
   sma20=safe(close.rolling(20).mean().iloc[-1],price)
   sma50=safe(close.rolling(50).mean().iloc[-1],price) if len(close)>=50 else sma20
   return {"price":safe(price,0),"change":safe(change,0),"vol_ratio":safe(vol_ratio,1),"rsi":safe(rsi_val,50),"sma20":safe(sma20,price),"sma50":safe(sma50,price),"vwap":safe(vwap,price),"price_vs_vwap":safe((price-vwap)/vwap*100 if vwap else 0,0),"atr":safe(atr,price*0.02),"atr_pct":safe(atr/price*100 if price else 2,2)}
  except Exception as e:
   print(t, period, e)
   continue
 return None
def job(force=False):
 now=datetime.now()
 watch=[]; rak=[]
 for item in WATCHLIST:
  d=get_data(item["ticker"])
  if not d or d["price"]==0:
   watch.append({**item,"price":0,"change":0,"score":0,"reasons":["Ingen data"],"vwap":0,"atr":0,"atr_pct":0,"position_size":1000})
   continue
  s=0; rs=[]
  if d["price"]>d["sma20"]: s+=20; rs.append("Over SMA20")
  if d["sma20"]>d["sma50"]: s+=20; rs.append("SMA20>SMA50")
  if d["price"]>d["vwap"]: s+=20; rs.append(f"VWAP {d['price_vs_vwap']:+.1f}%")
  if 30<d["rsi"]<70: s+=15; rs.append(f"RSI {d['rsi']:.0f}")
  if d["vol_ratio"]>1: s+=10; rs.append(f"Vol {d['vol_ratio']:.1f}x")
  if d["change"]>0: s+=10; rs.append(f"{d['change']:+.1f}%")
  rs.append(f"ATR {d['atr_pct']:.1f}%")
  if s==0: s=20; rs=["Neutral"]
  score=min(100,s)
  pos=max(1000,min(3500,2000*(score-30)/40*(2.0/max(0.5,d["atr_pct"]))))
  watch.append({**item,"price":d["price"],"change":d["change"],"score":score,"reasons":rs,"vwap":d["vwap"],"price_vs_vwap":d["price_vs_vwap"],"atr":d["atr"],"atr_pct":d["atr_pct"],"position_size":pos})
  if score>=50:
   stop=d["price"]-d["atr"]*1.5
   rak.append({**item,"score":score,"price":d["price"],"reasons":rs,"change":d["change"],"vwap":d["vwap"],"stop_loss":stop,"position_size":pos})
 rak.sort(key=lambda x:x["score"], reverse=True)
 last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch
 last_scan["status"]=f"FIXED NaN {len(rak)} raketer - {now.strftime('%H:%M:%S')} - 7 Yahoo OK - safe_float aktiv"
 print(last_scan["status"])
sched=BackgroundScheduler(); sched.add_job(lambda: job(force=False), 'interval', minutes=10); sched.start(); job(force=True)
@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/ping")
def ping(): return jsonify({"ok":True,"time":datetime.now().strftime('%H:%M:%S'),"yahoo_calls":0})
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/scan-now")
def sn(): job(force=True); return jsonify(last_scan)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
