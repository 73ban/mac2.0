#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"
if /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_fetch_eastmoney_market_snapshot.py" \
  --date "$DATE" \
  --timeout 30 \
  --force; then
  exit 0
fi

mkdir -p "$ROOT/raw/04-市场数据/东方财富/$DATE"
cat > "$ROOT/raw/04-市场数据/东方财富/$DATE/market-snapshot-error.md" <<EOF
# $DATE 东方财富全市场快照失败

- 时间：$(date '+%F %T')
- 状态：东方财富 push2 当前从本机网络返回空响应或断开连接。
- 处理：保留为备用接口，不阻塞同花顺、通达信、tdxrs、腾讯行情主链。
- 下一步：下次定时任务自动重试。
EOF

exit 0
