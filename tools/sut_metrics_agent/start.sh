#!/usr/bin/env bash
# 启动被测监控采集器（交互选择平台地址 / Token，可复用上次配置）
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]] && [[ ! -f .venv/bin/python ]]; then
  echo "未找到虚拟环境，正在创建 .venv …"
  python3 -m venv .venv
  .venv/bin/pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
  .venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

exec .venv/bin/python agent_ctl.py start "$@"
