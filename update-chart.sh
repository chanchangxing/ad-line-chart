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

# 1 计算 A/D Line
LAST_DATE="2026-03-23"
if [ -f "$RESULT_FILE" ]; then
    LAST_DATE=$(python3 -c "
import json
with open('$RESULT_FILE') as f:
    data = json.load(f)
print(data['daily'][-1]['date'])
" 2>/dev/null || echo "2026-03-23")
fi

START_DATE="$LAST_DATE"
if [ "$START_DATE" = "$TODAY" ]; then
    echo "Data already up to date, skip calculation"
else
    echo "Fetching A/D Line data ($START_DATE ~ $TODAY)..."
    cd "$SCRIPTS_DIR"
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    fi
    python3 "$SCRIPTS_DIR/ad-line.py" "$START_DATE" "$TODAY" 2>&1
fi

# 2 获取上证指数
echo "Fetching Shanghai index..."
SH_JSON=$(curl -s --max-time 15 \
  "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2026-03-23,$TODAY,101,qfq" 2>/dev/null || echo "{}")

# 3 生成 HTML
echo "Generating chart..."
cd "$SCRIPTS_DIR"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

python3 << 'PYEOF'
import json, os, re, urllib.request, sys

result_file = os.path.expanduser("~/.openclaw/workspace/scripts/ad-line-result.json")
with open(result_file) as f:
    ad_data = json.load(f)

today = os.environ.get("TODAY", "2026-04-27")
sh_data = {}

# Try to fetch SH index data
sh_url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2026-03-23,{e},101,qfq".format(e=today)
try:
    req = urllib.request.Request(sh_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        sh_raw = json.loads(resp.read().decode("utf-8"))
    if sh_raw and "data" in sh_raw:
        kline = []
        for k in ["sh000001"]:
            if k in sh_raw.get("data", {}):
                kline = sh_raw["data"][k].get("qfqday", []) or sh_raw["data"][k].get("day", [])
                break
        for item in kline:
            date_str = item[0]
            close_val = float(item[2])
            sh_data[date_str] = close_val
    if sh_data:
        print("  SH index: OK ({n} days)".format(n=len(sh_data)))
    else:
        print("  SH index: empty response, using fallback")
except Exception as e:
    print("  SH index fetch failed: {err}, using fallback".format(err=e))

# Fallback data
if not sh_data:
    sh_data = {
        "2026-03-23": 3813.28, "2026-03-24": 3881.28, "2026-03-25": 3931.84,
        "2026-03-26": 3889.08, "2026-03-27": 3913.72, "2026-03-30": 3923.29,
        "2026-03-31": 3891.86, "2026-04-01": 3948.55, "2026-04-02": 3919.29,
        "2026-04-03": 3880.10, "2026-04-07": 3890.16, "2026-04-08": 3995.00,
        "2026-04-09": 3966.17, "2026-04-10": 3986.22, "2026-04-13": 3988.56,
        "2026-04-14": 4026.63, "2026-04-15": 4027.21, "2026-04-16": 4055.55,
        "2026-04-17": 4051.43, "2026-04-20": 4082.13, "2026-04-21": 4085.08,
        "2026-04-22": 4106.26, "2026-04-23": 4093.25, "2026-04-24": 4079.90,
    }

# Build data arrays
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

sh_data_short = {}
for k, v in sh_data.items():
    sh_data_short[k[5:]] = v

# Read template
template_file = os.path.expanduser("~/.openclaw/workspace/ad-line-chart/index.html")
with open(template_file) as f:
    html = f.read()

# Replace data
ad_str = json.dumps(daily_data, ensure_ascii=False, indent=2)
sh_str = json.dumps(sh_data_short, ensure_ascii=False, indent=2)
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
    r"2026-03-23 ~ [\d-]+",
    start_date + " ~ " + end_date,
    html
)

with open(template_file, "w") as f:
    f.write(html)

days = len(daily_data)
last_cum = daily_data[-1]["cum"]
print("Chart updated: {d} days, final A/D {cum:+d}".format(d=days, cum=last_cum))
PYEOF

# 4 推送至 GitHub
echo "Pushing to GitHub Pages..."
cd "$REPO_DIR"
git add index.html
if ! git diff --cached --quiet; then
    git commit -m "Daily A/D Line update - $(date +%Y-%m-%d)"
    git push origin main 2>&1
    echo "Pushed successfully!"
else
    echo "No changes to push"
fi

echo "Done! https://chanchangxing.github.io/ad-line-chart/"
