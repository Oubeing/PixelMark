#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PixelMark 像素标绘 —— 启动入口。

用法：
    python run.py
"""

import os
import sys

# 允许从任意工作目录启动：把项目根加入 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pixelmark.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
