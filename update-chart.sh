#!/usr/bin/env bash
# ============================================================
# A/D Line 图表自动更新脚本
# 每天收盘后运行，更新数据并推送到 GitHub Pages
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
WORKSPACE_DIR="$HOME/.openclaw/workspace"
SCRIPTS_DIR="$WORKSPACE_DIR/scripts"
RESULT_FILE="$SCRIPTS_DIR/ad-line-result.json"
VENV_DIR="$SCRIPTS_DIR/venv"
NVM_DIR="$HOME/.nvm"

# 加载 nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null 2>&1

export TZ="Asia/Shanghai"
TODAY=$(date +%Y-%m-%d)
WEEKDAY=$(date +%u)  # 1=Mon, 7=Sun

# 只在交易日运行（周一到周五）
if [ "$WEEKDAY" -ge 6 ]; then
    echo "Non-trading day, skip"
    exit 0
fi

echo "A/D Line auto update - $TODAY"

# 1 计算 A/D Line（全量重算，保证累计值正确）
if [ -f "$RESULT_FILE" ]; then
    LAST_DATE=$(python3 -c "
import json
with open('$RESULT_FILE') as f:
    data = json.load(f)
print(data['daily'][-1]['date'])
" 2>/dev/null || echo "")
    if [ "$LAST_DATE" = "$TODAY" ]; then
        echo "Data already up to date ($TODAY), skip calculation"
    else
        echo "Fetching A/D Line data (2026-03-23 ~ $TODAY)..."
        cd "$SCRIPTS_DIR"
        if [ -f "$VENV_DIR/bin/activate" ]; then
            source "$VENV_DIR/bin/activate"
        fi
        python3 "$SCRIPTS_DIR/ad-line.py" "2026-03-23" "$TODAY" 2>&1
    fi
else
    echo "Fetching A/D Line data (2026-03-23 ~ $TODAY)..."
    cd "$SCRIPTS_DIR"
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    fi
    python3 "$SCRIPTS_DIR/ad-line.py" "2026-03-23" "$TODAY" 2>&1
fi

# 2 生成 HTML（含上证指数收盘价 + MA150）
echo "Generating chart..."
cd "$SCRIPTS_DIR"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

python3 << 'PYEOF'
import json, os, re, sys
import akshare as ak
import pandas as pd
from datetime import date

# --- 读取 A/D Line 数据 ---
result_file = os.path.expanduser("~/.openclaw/workspace/scripts/ad-line-result.json")
with open(result_file) as f:
    ad_data = json.load(f)

# --- 获取上证指数全量历史 + 计算 MA150 ---
print("  Fetching SH index + MA150...")
df = ak.stock_zh_index_daily(symbol="sh000001")
df = df.sort_values("date").reset_index(drop=True)
df["ma150"] = df["close"].rolling(window=150).mean()

start_dt = date(2026, 3, 23)
chart_df = df[df["date"] >= start_dt].copy()

sh_data = {}
for _, row in chart_df.iterrows():
    d = row["date"]
    date_short = "{:02d}-{:02d}".format(d.month, d.day)
    close_val = round(float(row["close"]), 2)
    v = row["ma150"]
    ma150_val = round(float(v), 2) if pd.notna(v) else None
    sh_data[date_short] = {"close": close_val, "ma150": ma150_val}

print("  SH index + MA150: OK ({} days)".format(len(sh_data)))

# --- 获取沪铝期货数据 (2026-01-01 至今) ---
print("  Fetching SHFE Aluminum (AL0) futures...")
al_df = ak.futures_zh_daily_sina(symbol="AL0")
al_df["date"] = pd.to_datetime(al_df["date"])
al_df = al_df.sort_values("date").reset_index(drop=True)
al_2026 = al_df[al_df["date"] >= "2026-01-01"].copy()

al_data = {}
for _, row in al_2026.iterrows():
    d = row["date"]
    date_short = "{:02d}-{:02d}".format(d.month, d.day)
    al_data[date_short] = {
        "close": round(float(row["close"]), 2),
        "open": round(float(row["open"]), 2),
        "high": round(float(row["high"]), 2),
        "low": round(float(row["low"]), 2),
    }

print("  SHFE Aluminum: OK ({} days, {} ~ {})".format(
    len(al_2026),
    al_2026["date"].min().strftime("%Y-%m-%d"),
    al_2026["date"].max().strftime("%Y-%m-%d")
))

# --- 构建每日数据 ---
daily_data = []
for d in ad_data["daily"]:
    short_date = d["date"][5:]
    daily_data.append({
        "date": short_date,
        "up": d["advances"],
        "dn": d["declines"],
        "flat": d.get("unchanged", 0),
        "diff": d["diff"],
        "cum": d["cumulative"],
    })

# --- 更新 HTML ---
template_file = os.path.expanduser("~/.openclaw/workspace/ad-line-chart/index.html")
with open(template_file) as f:
    html = f.read()

ad_str = json.dumps(daily_data, ensure_ascii=False, indent=2)
sh_str = json.dumps(sh_data, ensure_ascii=False, indent=2)
al_str = json.dumps(al_data, ensure_ascii=False, indent=2)
start_date = ad_data["start"]
end_date = ad_data["end"]

html = re.sub(
    r"const adData = \[.*?\];",
    "const adData = " + ad_str + ";",
    html, flags=re.DOTALL
)
html = re.sub(
    r"const shIndexData = \{.*?\};",
    "const shIndexData = " + sh_str + ";",
    html, flags=re.DOTALL
)
html = re.sub(
    r"const alFuturesData = \{.*?\};",
    "const alFuturesData = " + al_str + ";",
    html, flags=re.DOTALL
)
html = re.sub(
    r"2026-03-23 ~ [\d-]+",
    start_date + " ~ " + end_date,
    html
)

with open(template_file, "w") as f:
    f.write(html)

days = len(daily_data)
last_cum = daily_data[-1]["cum"]
print("Chart updated: {} days, final A/D {:>+d}".format(days, last_cum))
PYEOF

# 生成个股监控数据
echo "Generating stock data..."
cd "$REPO_DIR"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi
python3 generate_stocks.py 2>&1

# 3 推送至 GitHub
echo "Pushing to GitHub Pages..."
cd "$REPO_DIR"
git add index.html stocks.json generate_stocks.py update-stocks.sh
if ! git diff --cached --quiet; then
    git commit -m "Daily update - $(date +%Y-%m-%d)"
    git push origin main 2>&1
    echo "Pushed successfully!"
else
    echo "No changes to push"
fi

echo "Done! https://chanchangxing.github.io/ad-line-chart/"
