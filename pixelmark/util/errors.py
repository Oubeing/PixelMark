# -*- coding: utf-8 -*-
"""错误处理工具：统一异常类型、安全执行与全局异常钩子。"""

import sys
import traceback

from .logging import get_logger

logger = get_logger("errors")


class PixelMarkError(Exception):
    """PixelMark 业务异常的基类。"""


class ImageLoadError(PixelMarkError):
    """图像加载/解码失败。"""


class ImageSaveError(PixelMarkError):
    """图像保存失败。"""


class ScaleError(PixelMarkError):
    """比例尺标定参数非法。"""


def safe_call(func, *args, **kwargs):
    """执行 ``func``，吞掉异常并记录日志，返回 ``(ok, result_or_None)``。"""
    try:
        return True, func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 统一兜底
        logger.exception("安全调用失败 %s: %s", getattr(func, "__name__", func), exc)
        return False, None


def format_exc(exc):
    """把异常格式化为可展示的多行文本。"""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def install_excepthook(dialog_title="PixelMark 发生错误"):
    """安装全局异常钩子：记录日志并弹出友好对话框，避免程序静默崩溃。

    在 GUI 初始化阶段调用一次。返回原有的 excepthook 以便测试恢复。
    """
    original = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_tb))
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            if app is not None:
                detail = format_exc(exc_value)
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical)
                box.setWindowTitle(dialog_title)
                box.setText("程序遇到了一个未预期的错误，已被记录到日志文件。")
                box.setInformativeText("%s: %s" % (exc_type.__name__, exc_value))
                box.setDetailedText(detail)
                box.exec_()
        except Exception:  # noqa: BLE001 - 钩子自身绝不能再次抛异常
            logger.exception("异常钩子自身失败")

    sys.excepthook = _hook
    return original
