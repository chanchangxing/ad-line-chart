#!/usr/bin/env python3
"""
股票监控数据生成器
获取监控股票的技术指标，输出 stocks.json（供 GitHub Pages 使用）

指标：RSI(14) · MACD(12/26/9) · KDJ(9/3/3) · 布林带(20) · 均线 · RS评级
"""
import json, sys
import urllib.request
import math
from datetime import datetime

STOCKS = [
    {"code": "002050", "name": "三花智控", "market": "sz"},
    {"code": "002517", "name": "恺英网络", "market": "sz"},
    {"code": "603399", "name": "永杉锂业", "market": "sh"},
]

TENCENT_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SH_INDEX_SYMBOL = "sh000001"

OUTPUT_FILE = "/Users/chenchanghang/.openclaw/workspace/ad-line-chart/stocks.json"


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_klines(code, market, start="2026-01-01", end="2026-12-31"):
    """从腾讯 API 获取日线数据"""
    symbol = f"{market}{code}"
    today = datetime.now().strftime("%Y-%m-%d")
    params = f"param={symbol},day,{start},{today},101,qfq"
    url = f"{TENCENT_API}?{params}"
    try:
        j = fetch_json(url)
        data = j.get("data", {}).get(symbol, {})
        klines = data.get("qfqday") or data.get("day") or []
        return klines
    except Exception as e:
        print(f"    ⚠️ {symbol} K线获取失败: {e}", file=sys.stderr)
        return []


def fetch_realtime(code, market):
    """从腾讯实时 API 获取当前价格"""
    symbol = f"{market}{code}"
    url = f"https://qt.gtimg.cn/q={symbol}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("gbk")
        parts = text.split("~")
        if len(parts) > 40:
            return {
                "current": float(parts[3]) if parts[3] else None,
                "prev_close": float(parts[4]) if parts[4] else None,
                "open": float(parts[5]) if parts[5] else None,
                "volume": parts[6] if parts[6] else "0",
                "high": float(parts[33]) if parts[33] else None,
                "low": float(parts[34]) if parts[34] else None,
                "bid": float(parts[9]) if parts[9] else None,
                "ask": float(parts[19]) if parts[19] else None,
                "amount": parts[37] if parts[37] else "0",
                "change_pct": float(parts[32]) if parts[32] else 0,
                "change": float(parts[31]) if parts[31] else 0,
            }
    except Exception as e:
        print(f"    ⚠️ {symbol} 实时行情获取失败: {e}", file=sys.stderr)
    return None


def sma(values, n):
    """简单移动平均"""
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def ema(values, n):
    """指数移动平均 (EMA)，使用 SMA 作为初始值"""
    if len(values) < n:
        return [None] * len(values)
    k = 2 / (n + 1)
    result = [None] * len(values)
    # 初始值：SMA
    result[n-1] = sma(values[:n], n)
    for i in range(n, len(values)):
        result[i] = values[i] * k + result[i-1] * (1 - k)
    return result


def calc_rsi(closes, period=14):
    """RSI — Wilder 平滑算法"""
    if len(closes) < period + 1:
        return None
    
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def calc_macd(closes):
    """MACD (12/26/9)，SMA 初始值的 EMA 递推"""
    if len(closes) < 35:
        return None
    
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    
    difs = []
    for i in range(len(closes)):
        if ema12[i] is None or ema26[i] is None:
            difs.append(None)
        else:
            difs.append(ema12[i] - ema26[i])
    
    valid_difs = [d for d in difs if d is not None]
    if len(valid_difs) < 9:
        return None
    
    dea_vals = ema(valid_difs, 9)
    # 对齐索引
    offset = len(difs) - len(valid_difs)
    deas = [None] * offset + dea_vals
    
    latest_dif = valid_difs[-1]
    latest_dea = dea_vals[-1]
    macd_bar = 2 * (latest_dif - latest_dea)
    
    prev_dif = valid_difs[-2] if len(valid_difs) >= 2 else latest_dif
    prev_dea = dea_vals[-2] if len(dea_vals) >= 2 else latest_dea
    
    if prev_dif < prev_dea and latest_dif > latest_dea:
        signal = "金叉📈"
    elif prev_dif > prev_dea and latest_dif < latest_dea:
        signal = "死叉📉"
    elif latest_dif > latest_dea:
        signal = "多头📈"
    else:
        signal = "空头📉"
    
    return {
        "dif": round(latest_dif, 3),
        "dea": round(latest_dea, 3),
        "macd": round(macd_bar, 3),
        "signal": signal
    }


def calc_kdj(klines):
    """KDJ (9/3/3) — 递推平滑算法"""
    if len(klines) < 9:
        return None
    
    N = 9
    rsv_list = []
    
    for i in range(N - 1, len(klines)):
        window = klines[i - N + 1:i + 1]
        highs = [k[0] for k in window]  # [date, open, close, high, low, ...]
        lows = [k[0] for k in window]
        # K线格式: [date, open, close, high, low, volume, amount]
        # 腾讯 K线格式: [date, open, close, high, low, volume]
        # 需要确认...
        # 实际上腾讯 K线格式是: ["2026-05-08", "41.500", "41.980", "42.750", "41.500", "267015.00"]
        # 索引: 0=date, 1=open, 2=close, 3=high, 4=low, 5=volume
        h_vals = [float(k[3]) for k in window]
        l_vals = [float(k[4]) for k in window]
        close_val = float(window[-1][2])
        
        hh = max(h_vals)
        ll = min(l_vals)
        
        if hh == ll:
            rsv = 50.0
        else:
            rsv = (close_val - ll) / (hh - ll) * 100
        rsv_list.append(rsv)
    
    if not rsv_list:
        return None
    
    # 初始 K, D = 第一个 RSV
    k_vals = [rsv_list[0]]
    d_vals = [rsv_list[0]]
    
    for i in range(1, len(rsv_list)):
        k = k_vals[-1] * 2/3 + rsv_list[i] * 1/3
        d = d_vals[-1] * 2/3 + k * 1/3
        k_vals.append(k)
        d_vals.append(d)
    
    latest_k = k_vals[-1]
    latest_d = d_vals[-1]
    latest_j = 3 * latest_k - 2 * latest_d
    
    return {
        "k": round(latest_k, 1),
        "d": round(latest_d, 1),
        "j": round(latest_j, 1),
    }


def calc_bb(closes, period=20):
    """布林带 (总体标准差)"""
    if len(closes) < period:
        return None
    
    recent = closes[-period:]
    mid = sum(recent) / period
    
    squared_diff = [(x - mid) ** 2 for x in recent]
    std = math.sqrt(sum(squared_diff) / period) if sum(squared_diff) > 0 else 0
    
    return {
        "upper": round(mid + 2 * std, 2),
        "mid": round(mid, 2),
        "lower": round(mid - 2 * std, 2),
    }


def calc_mas(closes):
    """均线 MA5, MA10, MA20, MA60"""
    result = {}
    for n in [5, 10, 20, 60]:
        val = sma(closes, n)
        result[f"ma{n}"] = round(val, 2) if val else None
    return result


def calc_volume_ratio(klines, period=5):
    """量比（今日量 / 5日均量）"""
    if len(klines) < period + 1:
        return None
    volumes = [float(k[5]) for k in klines]
    avg_vol = sum(volumes[-(period+1):-1]) / period
    today_vol = volumes[-1]
    if avg_vol > 0:
        return round(today_vol / avg_vol, 2)
    return None


def calc_rs_rating(stock_closes, index_closes):
    """RS 评级：20日超额收益 vs 上证指数"""
    if len(stock_closes) < 21 or len(index_closes) < 21:
        return None
    
    stock_ret = (stock_closes[-1] - stock_closes[-21]) / stock_closes[-21] * 100
    index_ret = (index_closes[-1] - index_closes[-21]) / index_closes[-21] * 100
    excess = round(stock_ret - index_ret, 1)
    
    if excess > 15:
        emoji, rating = "🌟", "极强"
    elif excess > 5:
        emoji, rating = "📈", "强势"
    elif excess > -5:
        emoji, rating = "➡️", "中性"
    elif excess > -15:
        emoji, rating = "📉", "弱势"
    else:
        emoji, rating = "💀", "极弱"
    
    return {"emoji": emoji, "rating": rating, "excess": excess}


def calc_trend(mas, current, kdj, macd):
    """判断趋势方向"""
    if not mas or not current:
        return "数据不足"
    
    ma5 = mas.get("ma5")
    ma10 = mas.get("ma10")
    ma20 = mas.get("ma20")
    
    bullish = 0
    bearish = 0
    
    if current > ma20 if ma20 else False:
        bullish += 1
    else:
        bearish += 1
    
    if ma5 and ma10 and ma5 > ma10:
        bullish += 1
    else:
        bearish += 1
    
    if macd and macd["macd"] > 0:
        bullish += 1
    else:
        bearish += 1
    
    if kdj and kdj["j"] > 50:
        bullish += 1
    else:
        bearish += 1
    
    if bullish >= 3:
        return "强势上涨 📈"
    elif bullish >= 2:
        return "偏多震荡 ↗️"
    elif bearish >= 3:
        return "弱势下跌 📉"
    else:
        return "偏空震荡 ↘️"


def calc_signal(rsi, macd, kdj, bb, mas):
    """计算买卖信号评分"""
    score = 0
    reasons = []
    
    if rsi and rsi < 30:
        score += 2
        reasons.append("RSI超卖")
    elif rsi and rsi > 70:
        score -= 2
        reasons.append("RSI超买")
    
    if macd and macd["macd"] > 0:
        score += 2
        reasons.append("MACD多头")
    elif macd and macd["macd"] < 0:
        score -= 2
        reasons.append("MACD空头")
    
    if kdj and kdj["j"] < 20:
        score += 1
        reasons.append("KDJ超卖")
    elif kdj and kdj["j"] > 80:
        score -= 1
        reasons.append("KDJ超买")
    
    if bb and mas:
        current = mas.get("ma5", 0)
        if current < bb["lower"]:
            score += 1
            reasons.append("触及下轨")
        elif current > bb["upper"]:
            score -= 1
            reasons.append("触及上轨")
    
    if mas and mas.get("ma5") and mas.get("ma10"):
        if mas["ma5"] > mas["ma10"]:
            score += 1
            reasons.append("均线多头")
        else:
            score -= 1
            reasons.append("均线空头")
    
    if score >= 3:
        signal, emoji = "强烈买入", "🟢"
    elif score >= 1:
        signal, emoji = "偏多关注", "🟡"
    elif score >= -1:
        signal, emoji = "中性观望", "⚪"
    elif score >= -3:
        signal, emoji = "偏空谨慎", "🔴"
    else:
        signal, emoji = "强烈卖出", "💀"
    
    return {
        "score": score,
        "signal": signal,
        "emoji": emoji,
        "reasons": reasons
    }


def format_volume(vol_str):
    """格式化成交量显示"""
    try:
        v = float(vol_str)
        if v >= 1e8:
            return f"{v/1e8:.2f}亿"
        elif v >= 1e4:
            return f"{v/1e4:.0f}万"
        return vol_str
    except:
        return "N/A"


def format_amount(amt_str):
    """格式化成交额显示"""
    try:
        v = float(amt_str)
        if v >= 1e8:
            return f"{v/1e8:.2f}亿"
        elif v >= 1e4:
            return f"{v/1e4:.0f}万"
        return amt_str
    except:
        return "N/A"


def main():
    print("📊 生成股票监控数据...")
    
    # 先获取上证指数日线（用于 RS 评级）
    index_klines = fetch_klines("000001", "sh")
    index_closes = [float(k[2]) for k in index_klines] if index_klines else []
    
    results = []
    
    for stock in STOCKS:
        code = stock["code"]
        name = stock["name"]
        market = stock["market"]
        
        print(f"  🔍 {name} ({code})...")
        
        # 1. K线数据
        klines = fetch_klines(code, market)
        if not klines or len(klines) < 60:
            print(f"    ⚠️ 数据不足，跳过")
            results.append({"code": code, "name": name, "error": "数据不足"})
            continue
        
        closes = [float(k[2]) for k in klines]
        
        # 2. 实时行情
        rt = fetch_realtime(code, market)
        
        # 3. 技术指标
        rsi = calc_rsi(closes)
        macd = calc_macd(closes)
        kdj = calc_kdj(klines)
        bb = calc_bb(closes)
        mas = calc_mas(closes)
        vol_ratio = calc_volume_ratio(klines)
        rs = calc_rs_rating(closes, index_closes) if index_closes else None
        trend = calc_trend(mas, closes[-1], kdj, macd)
        signal = calc_signal(rsi, macd, kdj, bb, mas)
        
        # 4. 构建输出
        entry = {
            "code": code,
            "name": name,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        
        if rt:
            entry["current"] = rt["current"]
            entry["change"] = rt["change"]
            entry["change_pct"] = rt["change_pct"]
            entry["open"] = rt["open"]
            entry["prev_close"] = rt["prev_close"]
            entry["high"] = rt["high"]
            entry["low"] = rt["low"]
            entry["bid"] = rt["bid"]
            entry["ask"] = rt["ask"]
            entry["volume"] = format_volume(rt["volume"])
            entry["amount"] = format_amount(rt["amount"])
        else:
            # 回退：用最后一天K线
            last = klines[-1]
            entry["current"] = float(last[2])
            entry["prev_close"] = float(klines[-2][2]) if len(klines) >= 2 else float(last[2])
            entry["change"] = round(entry["current"] - entry["prev_close"], 2)
            entry["change_pct"] = round(entry["change"] / entry["prev_close"] * 100, 2) if entry["prev_close"] else 0
            entry["open"] = float(last[1])
            entry["high"] = float(last[3])
            entry["low"] = float(last[4])
            entry["bid"] = None
            entry["ask"] = None
            entry["volume"] = format_volume(last[5])
            entry["amount"] = "N/A"
        
        entry["rsi"] = rsi
        entry["macd"] = macd
        entry["kdj"] = kdj
        entry["bb"] = bb
        entry["mas"] = mas
        entry["vol_ratio"] = vol_ratio
        entry["rs"] = rs
        entry["trend"] = trend
        entry["signal"] = signal
        
        results.append(entry)
        print(f"    ✅ RSI={rsi}, MACD={macd['signal'] if macd else 'N/A'}, KDJ J={kdj['j'] if kdj else 'N/A'}")
    
    # 保存
    output = {
        "stocks": results,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results)
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存 {OUTPUT_FILE}（{len(results)} 只股票）")


if __name__ == "__main__":
    main()
