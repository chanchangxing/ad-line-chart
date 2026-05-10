#!/usr/bin/env bash
# ============================================================
# 个股监控 - 实时更新 stocks.json 到 GitHub Pages
# 工作日交易时段每 30 分钟执行
# 替代原来的 Telegram 推送，改为更新网站数据
# ============================================================
set -euo pipefail

REPO_DIR="$HOME/.openclaw/workspace/ad-line-chart"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export TZ="Asia/Shanghai"
TODAY=$(date +%Y-%m-%d)
WEEKDAY=$(date +%u)

# 只在交易日运行
if [ "$WEEKDAY" -ge 6 ]; then
    echo "$(date '+%H:%M:%S') Non-trading day, skip"
    exit 0
fi

cd "$REPO_DIR"

echo "$(date '+%H:%M:%S') 📊 更新个股监控..."

# 生成 stocks.json
python3 generate_stocks.py 2>&1
python3 generate_commodities.py 2>&1

# 检查是否有变化
if git diff --quiet stocks.json commodities.json; then
    echo "$(date '+%H:%M:%S') ✅ 数据无变化，跳过推送"
    exit 0
fi

# 推送
git add stocks.json commodities.json
git commit -m "📊 个股监控 $(date '+%m-%d %H:%M')" --quiet
git push origin main 2>&1

echo "$(date '+%H:%M:%S') ✅ 已推送 stocks.json"
echo "   https://chanchangxing.github.io/ad-line-chart/"
