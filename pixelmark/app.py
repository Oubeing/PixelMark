# -*- coding: utf-8 -*-
"""应用装配：日志、全局异常钩子、Qt 消息路由、主窗口。"""

import sys

from . import __app_name__, __version__
from .util.errors import install_excepthook
from .util.logging import get_logger, setup_logging

logger = get_logger("app")


def _install_qt_message_handler():
    """把 Qt 自身的警告/致命消息也写入日志。"""
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

        def _handler(mode, context, message):
            level = {
                QtMsgType.QtDebugMsg: logger.debug,
                QtMsgType.QtInfoMsg: logger.info,
                QtMsgType.QtWarningMsg: logger.warning,
                QtMsgType.QtCriticalMsg: logger.error,
                QtMsgType.QtFatalMsg: logger.critical,
            }.get(mode, logger.warning)
            level("Qt: %s (%s:%d)", message, context.file, context.line)

        qInstallMessageHandler(_handler)
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法安装 Qt 消息处理器: %s", exc)


def _configure_high_dpi():
    """高 DPI 屏幕适配（须在 QApplication 创建前设置）。"""
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法设置高 DPI 属性: %s", exc)


def create_app(argv=None):
    """创建 QApplication 并完成全局初始化（已存在实例时复用，便于测试）。"""
    from PyQt5.QtWidgets import QApplication

    argv = sys.argv if argv is None else argv
    _configure_high_dpi()
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("PixelMark")
    setup_logging()
    install_excepthook()
    _install_qt_message_handler()

    from .resources import init_resources
    init_resources()

    logger.info("%s v%s 启动（Python %s）", __app_name__, __version__,
                sys.version.split()[0])
    return app


def main(argv=None):
    app = create_app(argv)
    from .main_window import PixelMarkWindow

    window = PixelMarkWindow()
    window.showMaximized()   # 默认最大化，画布自动适应窗口
    logger.info("主窗口已显示")
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
