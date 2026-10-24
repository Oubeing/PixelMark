# -*- coding: utf-8 -*-
"""生成 README / 文档用截图（offscreen 无头环境）。

用法（项目根目录）：
    set QT_QPA_PLATFORM=offscreen
    python tools/make_screenshots.py

产出：
    docs/screenshots/main.png     主界面（载入示例图 + 测量标注，画布铺满绘图区）
    docs/screenshots/drawing.png  绘图演示（画笔/矩形/箭头 + 工具选项同屏）
    docs/screenshots/zoom.png     手动放大视图（滚动条 + 状态栏缩放）
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 无头环境缺少 Qt 自带字体目录时，指向系统字体目录（须在创建 QApplication 前设置）
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen
from PyQt5.QtWidgets import QApplication

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")


def make_sample_image():
    """构造一张 1400x900 的"工程样本图"：渐变底 + 标尺 + 几何元素。"""
    img = QImage(1400, 900, QImage.Format_RGB32)
    p = QPainter(img)
    # 渐变底（上浅下深）
    for y in range(900):
        t = y / 900.0
        p.setPen(QColor(int(245 - 40 * t), int(247 - 36 * t), int(250 - 30 * t)))
        p.drawLine(0, y, 1400, y)
    # 网格
    p.setPen(QPen(QColor(214, 220, 228), 1))
    for x in range(0, 1400, 50):
        p.drawLine(x, 0, x, 900)
    for y in range(0, 900, 50):
        p.drawLine(0, y, 1400, y)
    # 右侧"标尺"（已知长度参照，呼应比例尺标定场景）
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(250, 250, 252))
    p.drawRect(1120, 240, 240, 56)
    p.setPen(QPen(QColor(60, 64, 72), 2))
    p.drawRect(1120, 240, 240, 56)
    for i in range(11):
        x = 1120 + i * 24
        p.drawLine(x, 240, x, 240 + (14 if i % 5 == 0 else 8))
    # 几何元素
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(235, 87, 87, 210))
    p.drawEllipse(180, 150, 260, 260)
    p.setBrush(QColor(66, 133, 244, 200))
    p.drawRect(520, 180, 300, 200)
    p.setBrush(QColor(76, 175, 80, 200))
    pts = [(900, 420), (1060, 180), (1220, 420)]
    from PyQt5.QtCore import QPointF
    p.drawPolygon([QPointF(*pt) for pt in pts])
    # 左侧"工件"轮廓
    p.setPen(QPen(QColor(90, 96, 108), 3))
    p.setBrush(QColor(255, 255, 255, 160))
    p.drawRoundedRect(140, 560, 420, 260, 18, 18)
    p.setPen(QPen(QColor(120, 128, 140), 2))
    p.drawEllipse(220, 620, 80, 80)
    p.drawEllipse(400, 720, 80, 80)
    p.end()
    return img


def drag(canvas, p1, p2, button=Qt.LeftButton, steps=6):
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QEvent, QPointF

    def to_widget(px, py):
        r = canvas._image_rect()
        return QPoint(int(round(r.x() + px * canvas.zoom)),
                      int(round(r.y() + py * canvas.zoom)))

    a, b = to_widget(*p1), to_widget(*p2)
    press = QMouseEvent(QEvent.MouseButtonPress, a, button, button, Qt.NoModifier)
    canvas.mousePressEvent(press)
    for i in range(1, steps + 1):
        t = i / steps
        pos = QPoint(int(a.x() + (b.x() - a.x()) * t), int(a.y() + (b.y() - a.y()) * t)
                     )
        canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pos, button, button,
                                          Qt.NoModifier))
    canvas.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, b, button,
                                         button, Qt.NoModifier))


def add_measurements(win):
    """按公开 API 添加一组测量标注（含比例尺标定）。"""
    from pixelmark.measurement import (Scale, make_distance, make_rect_area,
                                       make_scalebar, make_text)
    board = win.board
    board.set_scale(Scale.from_lengths(240.0, 10.0, "mm"))   # 24 px/mm
    board.add_measurement(make_distance(QPoint(180, 430), QPoint(440, 430)))
    board.add_measurement(make_rect_area(QPoint(520, 180), QPoint(820, 380)))
    board.add_measurement(make_scalebar(QPoint(180, 850), QPoint(420, 850)))
    m = make_text(QPoint(620, 640), "缺陷 A：长度 10.83 mm")
    m.color = QColor(180, 40, 40)
    board.add_measurement(m)


def main():
    app = QApplication(sys.argv)

    from pixelmark.app import create_app
    from pixelmark.main_window import PixelMarkWindow
    from pixelmark.tools import ToolID

    create_app([])   # 复用同一 QApplication（日志/异常钩子）
    win = PixelMarkWindow()
    win.setGeometry(60, 40, 1440, 880)
    win.show()
    board = win.board

    img = make_sample_image()

    # ---- 1) 主界面（默认即"铺满绘图区"模式：无滚动条、边缘自动裁剪） ----
    board.load_image(img)
    add_measurements(win)
    win._select_tool(ToolID.DISTANCE)
    win.actionZoomFill.trigger()
    app.processEvents()
    win.grab().save(os.path.join(OUT_DIR, "main.png"))
    print("saved main.png", flush=True)

    # ---- 2) 绘图演示（真实鼠标事件走完整绘制管线） ----
    board.load_image(img)
    board.set_scale(Scale_from_lengths(240.0, 10.0, "mm"))
    add_measurements(win)
    win._select_tool(ToolID.PEN)
    board.pen_color = QColor(200, 30, 30)
    board.pen_size = 5
    drag(board, (120, 500), (180, 560))
    drag(board, (180, 560), (250, 520))
    win._select_tool(ToolID.RECT)
    board.pen_color = QColor(30, 90, 200)
    board.fill_shapes = True
    drag(board, (880, 560), (1120, 800))
    win._select_tool(ToolID.ARROW)
    board.pen_color = QColor(240, 140, 0)
    drag(board, (700, 620), (860, 560))
    win._select_tool(ToolID.PEN)   # 截图时显示画笔选项（粗细/颜色/平滑同屏）
    win.actionZoomFill.trigger()
    app.processEvents()
    win.grab().save(os.path.join(OUT_DIR, "drawing.png"))
    print("saved drawing.png", flush=True)

    # ---- 3) 手动放大视图（滚轮/工具放大到 200%，出现滚动条可拖动查看） ----
    win._select_tool(ToolID.DISTANCE)
    board.set_zoom(2.0, auto_fit=False)
    win.scrollArea.horizontalScrollBar().setValue(700)
    win.scrollArea.verticalScrollBar().setValue(260)
    app.processEvents()
    win.grab().save(os.path.join(OUT_DIR, "zoom.png"))
    print("saved zoom.png", flush=True)

    with open(os.path.join(OUT_DIR, "_gen_status.txt"), "w") as f:
        f.write("done")
    import os as _os
    _os._exit(0)


def Scale_from_lengths(px, real, unit):
    from pixelmark.measurement import Scale
    return Scale.from_lengths(px, real, unit)


if __name__ == "__main__":
    main()
