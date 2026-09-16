
from flask import Flask, jsonify, send_from_directory
from datetime import datetime, timedelta
import yfinance as yf, pandas as pd, json, os, math, re
from apscheduler.schedulers.background import BackgroundScheduler
import requests
app=Flask(__name__, static_folder='static')
BUDGET=10000
CACHE_FILE="/tmp/cache_ultimate_polara_v4.json"
PORTFOLIO_FILE="/tmp/portfolio_ultimate_polara_v4.json"
def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,"r") as f: return json.load(f)
    except: pass
    return d
def save_json(p,data):
    try:
        with open(p,"w") as f: json.dump(f,data)
    except: pass
portfolio=load_json(PORTFOLIO_FILE, {"start":BUDGET,"current":BUDGET,"trades":[],"total_pnl":0,"total_pnl_after":0,"total_courtage":0,"win_rate_after":0,"total":0,"wins_after":0,"daily_pnl":0})
cache=load_json(CACHE_FILE, {"raketer":[],"watchlist_prices":[],"news":[],"fi_insider":[],"blank_positions":[],"avanza_owners":[],"time":None})
last_scan={"budget":BUDGET,"max_daily_loss":500,"portfolio":portfolio,"raketer":cache.get("raketer",[]),"watchlist_prices":cache.get("watchlist_prices",[]),"news":cache.get("news",[]),"fi_insider":cache.get("fi_insider",[]),"blank_positions":cache.get("blank_positions",[]),"avanza_owners":cache.get("avanza_owners",[]),"news_count":len(cache.get("news",[])),"fi_count":len(cache.get("fi_insider",[])),"blank_count":len(cache.get("blank_positions",[])),"status":f"POLARA V4 ULTIMATE 7 KALLOR - cache {cache.get('time','aldrig')}","time":datetime.now().isoformat()}
WATCHLIST=[{"ticker":"SINCH.ST","name":"Sinch","fi_keywords":["Sinch"],"keywords":["sinch"],"avanza_id":5368},{"ticker":"EMBRAC-B.ST","name":"Embracer B","fi_keywords":["Embracer"],"keywords":["embracer"],"avanza_id":1015165},{"ticker":"BOL.ST","name":"Boliden","fi_keywords":["Boliden"],"keywords":["boliden"],"avanza_id":1570},{"ticker":"SAAB-B.ST","name":"Saab B","fi_keywords":["Saab"],"keywords":["saab"],"avanza_id":5411},{"ticker":"VOLV-B.ST","name":"Volvo B","fi_keywords":["Volvo"],"keywords":["volvo"],"avanza_id":853},{"ticker":"INVE-B.ST","name":"Investor B","fi_keywords":["Investor"],"keywords":["investor"],"avanza_id":1199},{"ticker":"NIBE-B.ST","name":"Nibe B","fi_keywords":["Nibe"],"keywords":["nibe"],"avanza_id":2605}]
def safe_float(x,fb=0):
    try:
        if x is None: return fb
        if isinstance(x,float) and (math.isnan(x) or math.isinf(x)): return fb
        if pd.isna(x): return fb
        return float(x)
    except: return fb
def analyze_news(t):
    if not t: return 0
    tl=t.lower(); s=0
    if any(k in tl for k in ["insider","vd köper","storägare"]): s+=20
    if any(k in tl for k in ["order","avtal","förvärv"]): s+=15
    if any(k in tl for k in ["överträffar","stark","rekord"]): s+=10
    if any(k in tl for k in ["vinstvarning","sänker","förlust"]): s-=20
    return max(-20,min(20,s))
def get_news():
    all_n=[]
    for item in WATCHLIST:
        try:
            t=yf.Ticker(item["ticker"])
            ynews=t.news if hasattr(t,'news') else []
            for n in ynews[:5]:
                title=n.get('title','')
                if not title: continue
                if any(kw.lower() in title.lower() for kw in item["keywords"]) or item["name"].lower() in title.lower():
                    score=analyze_news(title)
                    if score!=0 or "order" in title.lower():
                        all_n.append({"ticker":item["name"],"title":title[:120],"publisher":n.get('publisher','Yahoo'),"score":score,"timestamp":n.get('providerPublishTime',0)})
        except: pass
    all_n.sort(key=lambda x:x["score"], reverse=True)
    return all_n[:15]
def get_fi():
    fi=[]
    try:
        for item in WATCHLIST:
            t=yf.Ticker(item["ticker"])
            ynews=t.news if hasattr(t,'news') else []
            for n in ynews[:10]:
                title=n.get('title','')
                if not title: continue
                tl=title.lower()
                if any(k in tl for k in ["insider","insyn","vd köper","vd har köpt","storägare","insynshandel"]):
                    if any(kw.lower() in tl for kw in item["fi_keywords"]) or item["name"].lower() in tl:
                        amount=1000000
                        m=re.search(r'(\d+[\.,]?\d*)\s*(M|milj)', tl)
                        if m:
                            try:
                                val=float(m.group(1).replace(',','.'))
                                amount=val*1000000
                            except: pass
                        role="VD" if "vd" in tl else "Styrelse" if "styrelse" in tl else "Insider"
                        fi.append({"issuer":item["name"],"name":"Insider via FI","role":role,"type":"BUY","quantity":int(amount/100),"price":100,"total":amount,"date":datetime.now().strftime('%Y-%m-%d'),"title":title[:80],"score":25 if role=="VD" else 20})
    except: pass
    seen=set(); dedup=[]
    for f in fi:
        key=(f["issuer"], f["title"][:30])
        if key not in seen:
            seen.add(key); dedup.append(f)
    return dedup[:10]
def get_blank():
    blanks=[]
    for item in WATCHLIST:
        try:
            t=yf.Ticker(item["ticker"])
            info=t.info if hasattr(t,'info') else {}
            sp=info.get('shortPercentOfFloat') or info.get('sharesShortPercent') or 0
            sp=safe_float(sp,0)*100
            if sp>0:
                score=0
                if sp<1: score=10
                elif sp>3: score=-10
                if score!=0:
                    blanks.append({"issuer":item["name"],"short_percent":round(sp,2),"change":0,"score":score,"date":datetime.now().strftime('%Y-%m-%d'),"holder":"Flera","title":f"Short {sp:.2f}%"})
        except: pass
    return blanks
def get_avanza():
    owners=[]
    for item in WATCHLIST:
        try:
            aid=item.get("avanza_id")
            if not aid: continue
            r=requests.get(f"https://www.avanza.se/_mobile/market/stock/{aid}", headers={"User-Agent":"Mozilla/5.0"}, timeout=3)
            if r.status_code==200:
                j=r.json()
                num=j.get("numberOfOwners",0)
                if num>0:
                    prev=0
                    if cache.get("avanza_owners"):
                        for pr in cache.get("avanza_owners",[]):
                            if pr["name"]==item["name"]:
                                prev=pr["owners"]; break
                    trend=1 if num>prev and prev>0 else 0
                    score=5 if trend>0 else 0
                    owners.append({"name":item["name"],"owners":num,"prev":prev,"trend":trend,"score":score,"avanza_id":aid})
        except: pass
    return owners
def get_data(ticker):
    for period in ["6mo","1y","3mo"]:
        try:
            t=yf.Ticker(ticker)
            df=t.history(period=period, auto_adjust=True)
            if df.empty or len(df)<20: continue
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
            analyst_score=0
            try:
                recs=t.recommendations
                if recs is not None and not recs.empty:
                    if 'Buy' in str(recs.values): analyst_score=10
            except: pass
            return {"price":safe_float(price,0),"change":safe_float(change,0),"vol_ratio":safe_float(vol_ratio,1),"rsi":safe_float(rsi_val,50),"sma20":safe_float(sma20,price),"sma50":safe_float(sma50,price),"vwap":safe_float(vwap,price),"price_vs_vwap":safe_float((price-vwap)/vwap*100 if vwap else 0,0),"atr":safe_float(atr,price*0.02),"atr_pct":safe_float(atr/price*100 if price else 2.0,2.0),"analyst_score":analyst_score}
        except: continue
    return None
def kelly(score, atr_pct):
    base=BUDGET*0.2
    sf=max(0.5,min(1.5,(score-30)/40))
    af=max(0.5,min(1.5,2.0/max(0.5,atr_pct)))
    pos=base*sf*af
    return max(BUDGET*0.1, min(BUDGET*0.35, pos))
def job(force=False):
    global cache
    if not force and cache.get("time"):
        try:
            ct=datetime.fromisoformat(cache["time"])
            if datetime.now()-ct < timedelta(minutes=5):
                last_scan["status"]=f"POLARA V4 ULTIMATE CACHE {len(cache.get('raketer',[]))} raketer + {len(cache.get('news',[]))} nyheter + {len(cache.get('fi_insider',[]))} FI + {len(cache.get('blank_positions',[]))} blank - {ct.strftime('%H:%M:%S')} - 0 anrop"
                last_scan["raketer"]=cache.get("raketer",[]); last_scan["watchlist_prices"]=cache.get("watchlist_prices",[]); last_scan["news"]=cache.get("news",[]); last_scan["fi_insider"]=cache.get("fi_insider",[]); last_scan["blank_positions"]=cache.get("blank_positions",[]); last_scan["avanza_owners"]=cache.get("avanza_owners",[]); last_scan["news_count"]=len(cache.get("news",[])); last_scan["fi_count"]=len(cache.get("fi_insider",[])); last_scan["blank_count"]=len(cache.get("blank_positions",[])); return
        except: pass
    now=datetime.now()
    print(f"POLARA V4 ULTIMATE SCAN at {now}")
    news=get_news(); fi_ins=get_fi(); blank=get_blank(); avanza=get_avanza()
    news_map={}
    for n in news:
        if n["ticker"] not in news_map or n["score"]>news_map[n["ticker"]]["score"]:
            news_map[n["ticker"]]=n
    fi_map={}
    for f in fi_ins:
        if f["issuer"] not in fi_map or f["score"]>fi_map[f["issuer"]].get("score",0):
            fi_map[f["issuer"]]=f
    blank_map={}
    for b in blank:
        if b["issuer"] not in blank_map:
            blank_map[b["issuer"]]=b
    avanza_map={}
    for a in avanza:
        avanza_map[a["name"]]=a
    watch=[]; rak=[]
    for item in WATCHLIST:
        d=get_data(item["ticker"])
        news_item=news_map.get(item["name"]); news_score=news_item["score"] if news_item else 0; news_title=news_item["title"] if news_item else ""
        fi_item=fi_map.get(item["name"]); fi_score=fi_item["score"] if fi_item else 0; fi_title=fi_item["title"] if fi_item else ""; fi_role=fi_item["role"] if fi_item else ""; fi_amount=fi_item["total"] if fi_item else 0
        blank_item=blank_map.get(item["name"]); blank_score=blank_item["score"] if blank_item else 0; blank_title=blank_item["title"] if blank_item else ""
        avanza_item=avanza_map.get(item["name"]); avanza_score=avanza_item["score"] if avanza_item else 0; avanza_trend=avanza_item["trend"] if avanza_item else 0; owners=avanza_item["owners"] if avanza_item else 0
        if not d or d["price"]==0:
            watch.append({**item,"price":0,"change":0,"score":0,"reasons":["Ingen data"],"vwap":0,"atr":0,"atr_pct":0,"position_size":1000,"news_score":news_score,"news_title":news_title,"fi_score":fi_score,"fi_title":fi_title,"fi_role":fi_role,"fi_amount":fi_amount,"blank_score":blank_score,"blank_title":blank_title,"owners":owners,"owners_trend":avanza_trend,"analyst_score":0})
            continue
        s=0; rs=[]
        if d["price"]>d["sma20"]: s+=20; rs.append("Over SMA20")
        if d["sma20"]>d["sma50"]: s+=20; rs.append("SMA20>SMA50")
        if d["price"]>d["vwap"]: s+=20; rs.append(f"VWAP {d['price_vs_vwap']:+.1f}%")
        if 30<d["rsi"]<70: s+=15; rs.append(f"RSI {d['rsi']:.0f}")
        if d["vol_ratio"]>1: s+=10; rs.append(f"Vol {d['vol_ratio']:.1f}x")
        if d["change"]>0: s+=10; rs.append(f"{d['change']:+.1f}%")
        rs.append(f"ATR {d['atr_pct']:.1f}%")
        if news_score!=0: s+=news_score; rs.append(f"Nyhet +{news_score}")
        if fi_score!=0: s+=fi_score; rs.append(f"FI {fi_role} +{fi_score} {fi_amount/1000000:.1f}M")
        if blank_score!=0: s+=blank_score; rs.append(f"Blank {blank_score:+d}")
        if avanza_score!=0: s+=avanza_score; rs.append(f"Avanza ↑ +{avanza_score}")
        if d.get("analyst_score",0)!=0: s+=d["analyst_score"]; rs.append(f"Analyst +{d['analyst_score']}")
        if s==0: s=20; rs=["Neutral"]
        score=max(0, min(100, s))
        pos=kelly(score, d["atr_pct"])
        watch.append({**item,"price":d["price"],"change":d["change"],"score":score,"reasons":rs,"vwap":d["vwap"],"price_vs_vwap":d["price_vs_vwap"],"atr":d["atr"],"atr_pct":d["atr_pct"],"position_size":pos,"rsi":d["rsi"],"news_score":news_score,"news_title":news_title,"fi_score":fi_score,"fi_title":fi_title,"fi_role":fi_role,"fi_amount":fi_amount,"blank_score":blank_score,"blank_title":blank_title,"owners":owners,"owners_trend":avanza_trend,"analyst_score":d.get("analyst_score",0)})
        if score>=50:
            stop=d["price"]-d["atr"]*1.5
            rak.append({**item,"score":score,"price":d["price"],"reasons":rs,"change":d["change"],"vwap":d["vwap"],"atr":d["atr"],"stop_loss":stop,"position_size":pos,"news_score":news_score,"news_title":news_title,"fi_score":fi_score,"fi_title":fi_title,"fi_role":fi_role,"fi_amount":fi_amount,"blank_score":blank_score,"blank_title":blank_title,"owners":owners})
    rak.sort(key=lambda x:x["score"], reverse=True)
    last_scan["time"]=now.isoformat(); last_scan["raketer"]=rak; last_scan["watchlist_prices"]=watch; last_scan["news"]=news; last_scan["news_count"]=len(news); last_scan["fi_insider"]=fi_ins; last_scan["fi_count"]=len(fi_ins); last_scan["blank_positions"]=blank; last_scan["blank_count"]=len(blank); last_scan["avanza_owners"]=avanza; last_scan["portfolio"]=portfolio
    last_scan["status"]=f"POLARA V4 ULTIMATE LIVE {len(rak)} raketer + {len(news)} nyheter + {len(fi_ins)} FI + {len(blank)} blank + {len(avanza)} ägare - {now.strftime('%H:%M:%S')} - 7 KÄLLOR - FULL POLARA DESIGN"
    cache={"raketer":rak,"watchlist_prices":watch,"news":news,"fi_insider":fi_ins,"blank_positions":blank,"avanza_owners":avanza,"time":now.isoformat()}
    save_json(CACHE_FILE, cache); save_json(PORTFOLIO_FILE, portfolio)
    print(last_scan["status"])
sched=BackgroundScheduler(); sched.add_job(lambda: job(force=False), 'interval', minutes=10); sched.start(); job(force=True)
@app.route("/")
def idx(): return send_from_directory('static','index.html')
@app.route("/api/ping")
def ping(): return jsonify({"ok":True,"time":datetime.now().strftime('%H:%M:%S'),"yahoo_calls":0,"sources":7})
@app.route("/api/status")
def st(): return jsonify(last_scan)
@app.route("/api/scan-now")
def sn(): job(force=True); return jsonify(last_scan)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
