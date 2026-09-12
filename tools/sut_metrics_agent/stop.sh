#!/usr/bin/env bash
# 停止被测监控采集器
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .venv/bin/python ]]; then
  exec .venv/bin/python agent_ctl.py stop
fi
exec python3 agent_ctl.py stop
