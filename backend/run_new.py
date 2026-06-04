#!/usr/bin/env python3
"""
新版后端启动脚本
"""
import sys
import os
from pathlib import Path

# 加载环境变量：backend/.env 优先，其次项目根目录 .env
try:
    from dotenv import load_dotenv
    _backend_dir = Path(__file__).resolve().parent
    load_dotenv(_backend_dir / ".env")
    load_dotenv(_backend_dir.parent / ".env")
except ImportError:
    pass

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 从新结构导入并运行
from app.main import app
import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
