#!/usr/bin/env python3
"""
大宗商品监控 - 生猪期货 + 其他农产品
数据源：AKShare → 大连商品交易所 / 郑州商品交易所
输出：commodities.json
"""
import akshare as ak
import json, datetime, os

OUTPUT_FILE = os.path.expanduser("~/.openclaw/workspace/ad-line-chart/commodities.json")
now = datetime.datetime.now()
updated_at = now.strftime("%Y-%m-%d %H:%M")

commodities = []

# ─── 1. 生猪期货 ───
print("🐷 生猪...")
lh_all = []
try:
    df = ak.futures_zh_realtime(symbol='生猪')
    for _, row in df.iterrows():
        symbol = row.get('symbol', '')
        lh_all.append({
            "symbol": symbol,
            "name": row.get('name', '生猪'),
            "trade": float(row.get('trade', 0)),
            "preclose": float(row.get('preclose', 0)),
            "open": float(row.get('open', 0)),
            "high": float(row.get('high', 0)),
            "low": float(row.get('low', 0)),
            "settlement": float(row.get('settlement', 0)),
            "volume": int(row.get('volume', 0)) if not isinstance(row.get('volume', ''), str) else 0,
            "position": int(row.get('position', 0)) if not isinstance(row.get('position', ''), str) else 0,
            "change_pct": float(row.get('changepercent', 0)) * 100,
            "tradedate": str(row.get('tradedate', ''))
        })
    
    if lh_all:
        lh_main = lh_all[0]
        # 换算
        price_ton = lh_main['trade']
        price_kg = round(price_ton / 1000, 2)
        price_jin = round(price_ton / 2000, 2)
        
        commodities.append({
            "id": "pig_futures",
            "name": "生猪 LH",
            "emoji": "🐷",
            "unit": "元/吨",
            "trade": price_ton,
            "preclose": lh_main['preclose'],
            "open": lh_main['open'],
            "high": lh_main['high'],
            "low": lh_main['low'],
            "settlement": lh_main['settlement'],
            "volume": lh_main['volume'],
            "position": lh_main['position'],
            "change_pct": lh_main['change_pct'],
            "tradedate": lh_main.get('tradedate', ''),
            "converts": {
                "per_kg": price_kg,
                "per_jin": price_jin,
                "per_ton": price_ton
            },
            "sub_contracts": lh_all[1:]
        })
        print(f"  ✅ {lh_main.get('name','')} 收盘 ¥{price_ton} ({lh_main['change_pct']:+.2f}%)")
except Exception as e:
    print(f"  ⚠️ {e}")
    commodities.append({"id": "pig_futures", "name": "生猪 LH", "emoji": "🐷", "error": str(e)})

# ─── 2. 豆粕期货 ───
print("🌾 豆粕...")
try:
    df = ak.futures_zh_realtime(symbol='豆粕')
    if len(df) > 0:
        row = df.iloc[0]
        trade = float(row.get('trade', 0))
        preclose = float(row.get('preclose', 0))
        chg = float(row.get('changepercent', 0)) * 100
        commodities.append({
            "id": "soybean_meal",
            "name": "豆粕 M",
            "emoji": "🌾",
            "unit": "元/吨",
            "trade": trade,
            "preclose": preclose,
            "open": float(row.get('open', 0)),
            "high": float(row.get('high', 0)),
            "low": float(row.get('low', 0)),
            "volume": int(row.get('volume', 0)) if not isinstance(row.get('volume', ''), str) else 0,
            "position": int(row.get('position', 0)) if not isinstance(row.get('position', ''), str) else 0,
            "change_pct": chg,
            "tradedate": str(row.get('tradedate', ''))
        })
        print(f"  ✅ 豆粕 ¥{trade} ({chg:+.2f}%)")
except Exception as e:
    print(f"  ⚠️ {e}")
    commodities.append({"id": "soybean_meal", "name": "豆粕 M", "emoji": "🌾", "error": str(e)})

# ─── 3. 玉米期货 ───
print("🌽 玉米...")
try:
    df = ak.futures_zh_realtime(symbol='玉米')
    if len(df) > 0:
        row = df.iloc[0]
        trade = float(row.get('trade', 0))
        chg = float(row.get('changepercent', 0)) * 100
        commodities.append({
            "id": "corn",
            "name": "玉米 C",
            "emoji": "🌽",
            "unit": "元/吨",
            "trade": trade,
            "preclose": float(row.get('preclose', 0)),
            "open": float(row.get('open', 0)),
            "high": float(row.get('high', 0)),
            "low": float(row.get('low', 0)),
            "volume": int(row.get('volume', 0)) if not isinstance(row.get('volume', ''), str) else 0,
            "position": int(row.get('position', 0)) if not isinstance(row.get('position', ''), str) else 0,
            "change_pct": chg,
            "tradedate": str(row.get('tradedate', ''))
        })
        print(f"  ✅ 玉米 ¥{trade} ({chg:+.2f}%)")
except Exception as e:
    print(f"  ⚠️ {e}")
    commodities.append({"id": "corn", "name": "玉米 C", "emoji": "🌽", "error": str(e)})

output = {"updated_at": updated_at, "commodities": commodities}

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 已保存 {OUTPUT_FILE} ({len(commodities)} 个品种)")
