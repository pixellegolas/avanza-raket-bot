
import pandas as pd, ta
def calculate_rocket_score(df: pd.DataFrame):
    if len(df) < 200:
        return 0, ["For lite data"]
    last = df.iloc[-1]
    reasons = []
    score = 0
    rsi = ta.momentum.rsi(df['Close'], 14).iloc[-1]
    if 55 <= rsi <= 75:
        score += 25
        reasons.append(f"RSI {rsi:.0f} stark men ej overkopt")
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    rel_vol = last['Volume'] / avg_vol if avg_vol else 0
    if rel_vol > 2.5:
        score += 30
        reasons.append(f"RelVol {rel_vol:.1f}x")
    ma50 = df['Close'].rolling(50).mean().iloc[-1]
    ma150 = df['Close'].rolling(150).mean().iloc[-1]
    ma200 = df['Close'].rolling(200).mean().iloc[-1]
    if last['Close'] > ma50 > ma150 > ma200:
        score += 25
        reasons.append("Trend Template OK")
    high_20 = df['Close'].rolling(20).max().iloc[-2]
    if last['Close'] > high_20:
        score += 20
        reasons.append(f"Breakout over 20d {high_20:.1f}")
    return min(score, 100), reasons
