# -*- coding: utf-8 -*-
"""统一的日志配置。

日志同时输出到控制台与滚动文件（默认 ``<项目>/logs/pixelmark_YYYYMMDD_HHMMSS.log``），
项目目录不可写时自动退回到系统临时目录，保证任何环境下都能记录日志。
"""

import logging
import os
import sys
import tempfile
from datetime import datetime
from logging.handlers import RotatingFileHandler

_LOGGER_NAME = "pixelmark"
_CONFIGURED = False

LOG_FORMAT = "%(asctime)s [%(levelname)7s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _default_log_dir():
    """优先使用项目下的 logs/ 目录，不可写时退回临时目录。"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(project_root, "logs")
    try:
        os.makedirs(candidate, exist_ok=True)
        probe = os.path.join(candidate, ".writable")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return candidate
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "pixelmark_logs")
        try:
            os.makedirs(fallback, exist_ok=True)
            return fallback
        except OSError:
            return None


def setup_logging(log_dir=None, level=logging.INFO, console=True):
    """初始化日志系统（幂等，可重复调用）。

    Returns:
        logging.Logger: 根 logger ``pixelmark``。
    """
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    if log_dir is None:
        log_dir = _default_log_dir()
    if log_dir:
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(log_dir, "pixelmark_%s.log" % stamp)
            handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024,
                                          backupCount=5, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except OSError as exc:  # pragma: no cover - 极端环境
            sys.stderr.write("无法创建日志文件: %s\n" % exc)

    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        logger.addHandler(stream)

    _CONFIGURED = True
    return logger


def get_logger(name=None):
    """获取子 logger，例如 ``get_logger('canvas')``。"""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(_LOGGER_NAME if not name else "%s.%s" % (_LOGGER_NAME, name))
