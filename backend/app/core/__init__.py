"""
核心模块
"""
from .config import *
from .auth import *
from .security import *

# 为了兼容旧导入，导出 settings
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from . import config
settings = config
