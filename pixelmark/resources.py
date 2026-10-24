# -*- coding: utf-8 -*-
"""资源加载：优先使用编译的 Qt 资源（img_resources.py），失败时回退到磁盘文件。

这样即使忘记运行 pyrcc 重新编译资源，或从其他工作目录启动，图标依然可用。
"""

import os

from PyQt5.QtGui import QIcon, QPixmap

from .util.logging import get_logger

logger = get_logger("resources")

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
IMG_DIR = os.path.join(PROJECT_ROOT, "img")

_RESOURCE_PREFIX = ":/img/img/"


def _load_compiled_resources():
    """导入 pyrcc5 编译出的资源模块（幂等）。"""
    try:
        import img_resources  # noqa: F401
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("编译资源不可用（%s），将从磁盘加载图标", exc)
        return False


def init_resources():
    """在创建任何窗口前调用一次。"""
    ok = _load_compiled_resources()
    if not ok and not os.path.isdir(IMG_DIR):
        logger.error("既无编译资源也无图标目录，界面图标将缺失")
    return ok


def icon(name):
    """按名称（不含扩展名）获取 QIcon，资源优先、磁盘回退。"""
    path = _RESOURCE_PREFIX + name + ".png"
    ic = QIcon(path)
    if not ic.isNull():
        return ic
    disk = os.path.join(IMG_DIR, name + ".png")
    if os.path.exists(disk):
        return QIcon(disk)
    logger.warning("图标不存在: %s", name)
    return QIcon()


def pixmap(name):
    path = _RESOURCE_PREFIX + name + ".png"
    pm = QPixmap(path)
    if not pm.isNull():
        return pm
    disk = os.path.join(IMG_DIR, name + ".png")
    if os.path.exists(disk):
        return QPixmap(disk)
    return QPixmap()
