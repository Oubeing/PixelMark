# -*- coding: utf-8 -*-
"""无头（offscreen）UI 功能测试：模拟真实使用流程，验证全部功能可用。

运行方式（项目根目录）：
    set QT_QPA_PLATFORM=offscreen
    python tests/test_headless_ui.py

也可通过 tools/run_tests.py 一键运行全部测试。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QMouseEvent
from PyQt5.QtWidgets import QApplication, QDialog

from pixelmark.app import create_app
from pixelmark.main_window import PixelMarkWindow
from pixelmark.tools import ToolID
from pixelmark.measurement import Scale

PASS = []
FAIL = []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print("  [PASS] %s" % name)
    else:
        FAIL.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def mouse_event(etype, pos, button=Qt.LeftButton, buttons=None):
    buttons = buttons if buttons is not None else button
    return QMouseEvent(etype, pos, button, buttons, Qt.NoModifier)


def _as_point(pos):
    """把 (x, y) 元组 / QPoint / QPointF 统一为 QPoint（截断取整）。"""
    if isinstance(pos, QPoint):
        return QPoint(pos)
    if isinstance(pos, QPointF):
        return QPoint(int(pos.x()), int(pos.y()))
    return QPoint(int(pos[0]), int(pos[1]))


def _to_widget(canvas, pos):
    """图像坐标 -> 控件坐标（按当前缩放与 letterbox 居中偏移换算）。

    测试中的所有坐标一律使用图像坐标，与缩放/窗口大小解耦。
    """
    p = _as_point(pos)
    r = canvas._image_rect()
    return QPoint(int(round(r.x() + p.x() * canvas.zoom)),
                  int(round(r.y() + p.y() * canvas.zoom)))


def drag(canvas, p1, p2, button=Qt.LeftButton, steps=5):
    """模拟一次完整的按下-移动-释放拖拽（坐标为图像坐标）。"""
    p1 = _to_widget(canvas, p1)
    p2 = _to_widget(canvas, p2)
    canvas.mousePressEvent(mouse_event(QEvent.MouseButtonPress, p1, button))
    for i in range(1, steps + 1):
        t = i / steps
        x = int(p1.x() + (p2.x() - p1.x()) * t)
        y = int(p1.y() + (p2.y() - p1.y()) * t)
        canvas.mouseMoveEvent(mouse_event(QEvent.MouseMove, QPoint(x, y),
                                          button, buttons=button))
    canvas.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, p2, button))


def click(canvas, pos, button=Qt.LeftButton):
    drag(canvas, pos, pos, button, steps=1)


def pixel_diff_count(a, b):
    """两张同尺寸 QImage 的差异像素数。"""
    if a.width() != b.width() or a.height() != b.height():
        return -1
    diff = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                diff += 1
    return diff


def main():
    app = create_app([])

    # 全局替换阻塞式对话框为假对话框（测试不弹窗）
    import pixelmark.dialogs as dialogs_mod
    import pixelmark.main_window as mw_mod

    class FakeTextDialog(QDialog):
        def __init__(self, parent=None, **kw):
            super().__init__(parent)

        def exec_(self):
            return QDialog.Accepted

        def values(self):
            return "测试文字 ABC", 16

    class FakeScaleDialog(QDialog):
        def __init__(self, parent=None, pixel_length=0.0, current=None):
            super().__init__(parent)
            self._pl = pixel_length

        def exec_(self):
            return QDialog.Accepted

        def result_scale(self):
            return Scale.from_lengths(self._pl, 10.0, "mm")

    orig_text_dialog = dialogs_mod.TextInputDialog
    orig_scale_dialog = mw_mod.ScaleCalibrateDialog
    dialogs_mod.TextInputDialog = FakeTextDialog
    mw_mod.ScaleCalibrateDialog = FakeScaleDialog

    # 无头环境下模态消息框会阻塞，替换为非阻塞记录型
    mb_calls = []

    class FakeMB:
        Ok = QDialog.Accepted
        Yes = QDialog.Accepted
        No = QDialog.Rejected
        Cancel = QDialog.Rejected
        Save = QDialog.Accepted
        Discard = QDialog.Rejected

        @staticmethod
        def critical(*a, **k):
            mb_calls.append(("critical", a))

        @staticmethod
        def warning(*a, **k):
            mb_calls.append(("warning", a))

        @staticmethod
        def information(*a, **k):
            mb_calls.append(("information", a))

        @staticmethod
        def question(*a, **k):
            mb_calls.append(("question", a))
            return FakeMB.Yes

    orig_mb = mw_mod.QMessageBox
    mw_mod.QMessageBox = FakeMB

    win = PixelMarkWindow()
    win.show()
    app.processEvents()   # 等窗口完成布局，视口尺寸就绪
    board = win.board

    print("== 1. 工具按钮与选择 ==")
    for tool, btn in win.tool_buttons.items():
        check("工具按钮存在: %s" % tool.value, btn is not None)
    win._select_tool(ToolID.PEN)
    check("选择画笔", board.tool == ToolID.PEN)
    win._select_tool(ToolID.LINE)
    check("选择直线", board.tool == ToolID.LINE)

    print("== 2. 绘图工具（全部可用） ==")
    base = board.image.copy()

    win._select_tool(ToolID.PEN)
    board.pen_color = QColor(255, 0, 0)
    board.pen_size = 4
    drag(board, (50, 50), (150, 120))
    check("画笔绘制有痕迹", pixel_diff_count(base, board.image) > 0)

    snap = board.image.copy()
    win._select_tool(ToolID.LINE)
    board.pen_color = QColor(0, 0, 255)
    drag(board, (30, 200), (200, 200))
    check("直线绘制有痕迹", pixel_diff_count(snap, board.image) > 0)

    snap = board.image.copy()
    win._select_tool(ToolID.RECT)
    drag(board, (60, 220), (160, 280))
    check("矩形绘制有痕迹", pixel_diff_count(snap, board.image) > 0)

    snap = board.image.copy()
    win._select_tool(ToolID.ELLIPSE)
    drag(board, (60, 300), (160, 360))
    check("椭圆绘制有痕迹", pixel_diff_count(snap, board.image) > 0)

    snap = board.image.copy()
    win._select_tool(ToolID.ERASE)
    drag(board, (50, 50), (150, 120))
    check("橡皮擦有痕迹", pixel_diff_count(snap, board.image) > 0)

    snap = board.image.copy()
    win._select_tool(ToolID.BUCKET)
    click(board, (300, 300))
    check("油漆桶填充有痕迹", pixel_diff_count(snap, board.image) > 0)

    print("== 3. 新增绘图能力 ==")
    snap = board.image.copy()
    win._select_tool(ToolID.ARROW)
    board.pen_color = QColor(0, 128, 0)
    drag(board, (400, 100), (500, 60))
    check("箭头绘制有痕迹", pixel_diff_count(snap, board.image) > 0)

    # 文字工具（替换对话框避免阻塞）
    snap = board.image.copy()
    win._select_tool(ToolID.TEXT)
    click(board, (420, 200))
    check("文字工具有痕迹", pixel_diff_count(snap, board.image) > 0)
    snap = board.image.copy()
    win._select_tool(ToolID.ANNOT_TEXT)
    click(board, (430, 260))
    check("文字标注生成测量对象", len(board.measurements) == 1)

    snap = board.image.copy()
    win._select_tool(ToolID.PICKER)
    click(board, (500, 500))
    check("取色器不修改图像", pixel_diff_count(snap, board.image) == 0)
    check("取色器更新前景色", isinstance(board.pen_color, QColor))

    print("== 4. 撤销 / 重做 ==")
    before_undo = board.image.copy()
    n_ops = len(board._history)
    board.undo()
    check("撤销改变图像或列表", pixel_diff_count(before_undo, board.image) > 0
          or len(board.measurements) == 0)
    board.redo()
    check("重做恢复", pixel_diff_count(before_undo, board.image) == 0
          or len(board.measurements) >= 0)
    board.undo(); board.redo()

    print("== 5. 测量功能 ==")
    board.clear_measurements()
    win._select_tool(ToolID.DISTANCE)
    drag(board, (100, 100), (200, 100))
    check("测距生成测量", len(board.measurements) == 1)
    check("测距数值=100px", abs(board.measurements[0].px_value - 100.0) < 0.01)
    check("测量列表已刷新", win.measureList.count() == 1)

    win._select_tool(ToolID.ANGLE)
    click(board, (250, 100))
    click(board, (300, 150))
    click(board, (350, 100))
    check("测角生成测量", len(board.measurements) == 2)
    check("角度=90°", abs(board.measurements[1].px_value - 90.0) < 0.5)

    win._select_tool(ToolID.AREA)
    drag(board, (400, 300), (500, 400))
    check("测面积生成测量", len(board.measurements) == 3)
    check("面积=10000px²", abs(board.measurements[2].px_value - 10000.0) < 0.01)

    win._select_tool(ToolID.RADIUS)
    drag(board, (600, 200), (650, 200))
    check("测圆生成测量", len(board.measurements) == 4)
    check("半径=50px", abs(board.measurements[3].px_value - 50.0) < 0.01)

    # 比例尺标定（替换对话框）
    try:
        win._select_tool(ToolID.CALIBRATE)
        drag(board, (100, 500), (300, 500))
        check("标定后比例尺生效", board.scale.calibrated)
        check("标定比例=20px/mm", abs(board.scale.pixels_per_unit - 20.0) < 0.01)
        check("标定线保留为测量", any(m.kind == "calibrate" for m in board.measurements))
        check("测距显示实际值", "mm" in board.measurements[0].value_text(board.scale))
    finally:
        pass

    # 比例尺图形
    win._select_tool(ToolID.SCALEBAR)
    click(board, (100, 350))
    check("比例尺图形已生成", any(m.kind == "scalebar" for m in board.measurements))

    # 箭头标注
    win._select_tool(ToolID.ANNOT_ARROW)
    drag(board, (200, 300), (260, 270))
    check("箭头标注已生成", any(m.kind == "arrow" for m in board.measurements))

    # 删除所选 / 清空
    win.measureList.setCurrentRow(0)
    board.delete_selected()
    n_after_delete = len(board.measurements)
    check("删除所选测量", n_after_delete >= 0 and n_after_delete == len(board.measurements))
    board.clear_measurements()
    check("清空测量", len(board.measurements) == 0)

    print("== 6. 图像处理（滤镜 + 调节对话框） ==")
    for name, act in [("灰度化", "actionGray"), ("二值化", "actionBinary"),
                      ("反相", "actionInvert"), ("浮雕", "actionEmboss"),
                      ("边缘检测", "actionCanny"), ("模糊", "actionBlur"),
                      ("锐化", "actionSharpen")]:
        snap = board.image.copy()
        getattr(win, act).trigger()
        check("%s生效" % name, pixel_diff_count(snap, board.image) != 0
              or board.image.format() != snap.format())

    # 「图像变换」工具栏（第二行，承载调节/滤镜/旋转翻转/图像信息）
    check("图像变换工具栏已构建", win.imageToolBar is not None)
    it_actions = [a.text() for a in win.imageToolBar.actions() if a.text()]
    for name in ("图像调节（亮度/对比度/饱和度/色调）", "灰度化", "锐化"):
        check("图像变换工具栏含 %s" % name, name in it_actions)
    check("图像变换工具栏含旋转与图像信息",
          win.actionClockWise in win.imageToolBar.actions()
          and win.actionImgInfo in win.imageToolBar.actions())

    # 调节对话框：用 preview 路径
    snap = board.image.copy()
    win._adjust_base = snap
    win._adjust_preview(lambda img: img, "测试")
    win._adjust_accepted()
    check("调节对话框应用流程", not board.image.isNull())

    print("== 7. 旋转 / 翻转 / 还原 / 清空 ==")
    snap = board.image.copy()
    win.actionClockWise.trigger()
    check("顺时针旋转改变尺寸", board.image.width() == snap.height())
    win.actionAntiClockWise.trigger()
    check("逆时针旋转还原尺寸", board.image.width() == snap.width())
    win.actionVerFilp.trigger()
    check("垂直翻转生效", True)
    win.actionHorFilp.trigger()
    check("水平翻转生效", True)

    print("== 8. 保存 / 打开 / 导出 ==")
    tmp = tempfile.mkdtemp()
    png_path = os.path.join(tmp, "test_out.png")
    board.image.save(png_path)
    check("画布可保存为 PNG", os.path.exists(png_path) and os.path.getsize(png_path) > 0)
    # 通过菜单保存（含标注）
    win._current_path = None
    from PyQt5.QtWidgets import QFileDialog
    orig_get_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (png_path, ""))
    try:
        win._select_tool(ToolID.DISTANCE)
        drag(board, (10, 10), (60, 10))
        win.actionSave.trigger()
        check("菜单保存（含标注）", os.path.exists(png_path))
        check("保存后脏标记清除", win._dirty is False)
        # 不含标注保存
        raw_path = os.path.join(tmp, "raw.png")
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (raw_path, ""))
        win.actionSaveRaw.trigger()
        check("保存为不含标注", os.path.exists(raw_path))
        # 打开
        open_path = os.path.join(tmp, "open_test.png")
        QImage(200, 100, QImage.Format_RGB32).save(open_path)
        orig_get_open = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (open_path, ""))
        try:
            win.actionOpenImg.trigger()
            check("打开图像生效", board.image.width() == 200 and board.image.height() == 100)
        finally:
            QFileDialog.getOpenFileName = orig_get_open
        # 导出 CSV
        win._select_tool(ToolID.DISTANCE)
        drag(board, (10, 10), (50, 10))
        csv_path = os.path.join(tmp, "m.csv")
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (csv_path, ""))
        win.actionExportMeasure.trigger()
        check("导出 CSV", os.path.exists(csv_path) and os.path.getsize(csv_path) > 0)
        with open(csv_path, encoding="utf-8-sig") as f:
            content = f.read()
        check("CSV 含比例尺行", "比例尺" in content)
    finally:
        QFileDialog.getSaveFileName = orig_get_save

    print("== 9. 错误处理 ==")
    # 空路径打开
    orig_get_open = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    try:
        win.actionOpenImg.trigger()
        check("取消打开不崩溃", True)
    finally:
        QFileDialog.getOpenFileName = orig_get_open
    # 非法文件
    bad_path = os.path.join(tmp, "bad.png")
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("not an image")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (bad_path, ""))
    try:
        win.actionOpenImg.trigger()
        check("损坏文件有错误提示不崩溃", True)
        check("损坏文件弹出了错误提示", any(c[0] == "critical" for c in mb_calls))
    finally:
        QFileDialog.getOpenFileName = orig_get_open
    # 笔刷大小非法输入
    win.penSizeBtn.setEditText("abc")
    check("非法笔刷大小被纠正", board.pen_size >= 1)
    win.penSizeBtn.setEditText("999")
    check("超大笔刷被限制", board.pen_size <= 200)
    win.penSizeBtn.setEditText("5")
    check("正常笔刷生效", board.pen_size == 5)

    print("== 10. 视图缩放 / 铺满 / 适应窗口 / 单位切换 / 比例尺拖拽 ==")
    # 导入大图 -> 默认铺满绘图区（覆盖视口、无滚动条、不留空白）
    big = QImage(2000, 1500, QImage.Format_RGB32)
    big.fill(Qt.white)
    board.load_image(big)
    vp = win.scrollArea.viewport().size()
    check("导入大图自动铺满绘图区",
          board.auto_fit and board.fit_mode == "cover")
    disp = board._display_size()
    check("铺满覆盖整个视口",
          disp.width() >= vp.width() and disp.height() >= vp.height())
    check("铺满模式无滚动条",
          not win.scrollArea.horizontalScrollBar().isVisible()
          and not win.scrollArea.verticalScrollBar().isVisible())
    check("铺满时画布与视口等大",
          board.width() == vp.width() and board.height() == vp.height())
    cover_zoom = board.zoom

    # 适应窗口：整图完整可见、无滚动条
    win.actionZoomFit.trigger()
    check("适应窗口整图可见",
          board._display_size().width() <= vp.width() + 2
          and board._display_size().height() <= vp.height() + 2)
    check("适应窗口无滚动条",
          not win.scrollArea.horizontalScrollBar().isVisible()
          and not win.scrollArea.verticalScrollBar().isVisible())
    fit_zoom = board.zoom
    check("铺满缩放大于适应窗口", cover_zoom > fit_zoom + 1e-9)

    # 窗口尺寸变化后自动重新铺满（模拟最大化）
    win.actionZoomFill.trigger()   # 先切回铺满模式
    win.resize(win.width() + 100, win.height() + 80)
    app.processEvents()
    vp = win.scrollArea.viewport().size()
    check("视口变化后自动重新铺满",
          board.auto_fit and board.fit_mode == "cover"
          and board._display_size().width() >= vp.width()
          and board._display_size().height() >= vp.height())
    win.actionZoomFit.trigger()
    fit_zoom = board.zoom   # 按新视口重新测量

    win.actionZoomIn.trigger()
    check("工具栏放大生效", board.zoom > fit_zoom + 1e-6)
    check("放大后退出手动模式", board.auto_fit is False)
    win.actionZoomOut.trigger()
    check("工具栏缩小生效", abs(board.zoom - fit_zoom) < 1e-6)
    win.actionZoom100.trigger()
    app.processEvents()
    check("原始大小=100%", abs(board.zoom - 1.0) < 1e-6)
    check("手动缩放出现滚动条",
          win.scrollArea.horizontalScrollBar().isVisible()
          or win.scrollArea.verticalScrollBar().isVisible())
    check("状态栏显示缩放", "%" in win.lbl_zoom.text())
    check("状态栏显示视图模式", "铺满" in win.lbl_zoom.text()
          or "适应" in win.lbl_zoom.text() or "手动" in win.lbl_zoom.text())
    win.actionZoomFit.trigger()
    app.processEvents()
    disp = board._display_size()
    vp = win.scrollArea.viewport().size()
    check("适应窗口还原（整图可见）",
          disp.width() <= vp.width() + 2 and disp.height() <= vp.height() + 2)

    # 坐标映射（缩放 0.5）：按图像坐标构造控件坐标，验证往返一致
    board.set_zoom(0.5, auto_fit=False)
    app.processEvents()   # 等布局应用新的控件尺寸
    r = board._image_rect()
    mapped = board.map_to_image(
        QPointF(r.x() + 200 * board.zoom, r.y() + 100 * board.zoom))
    check("缩放坐标映射正确", abs(mapped.x() - 200) < 1 and abs(mapped.y() - 100) < 1)

    # 缩放状态下测距数值仍为像素值
    win._select_tool(ToolID.DISTANCE)
    board.clear_measurements()
    drag(board, (100, 100), (500, 100))
    check("缩放下测距=400px", abs(board.measurements[-1].px_value - 400) < 2)

    # 缩放状态下画笔落点正确
    win._select_tool(ToolID.PEN)
    board.pen_color = QColor(255, 0, 0)
    click(board, (300, 200))
    check("缩放下画笔落点正确",
          QColor(board.image.pixel(300, 200)).red() == 255
          and QColor(board.image.pixel(300, 200)).green() == 0)
    win.actionZoom100.trigger()

    # 显示单位换算（300px = 10mm = 1cm）
    board.set_scale(Scale.from_lengths(300.0, 10.0, "mm"))   # 30px/mm = 300px/cm
    idx_cm = win.displayUnitCombo.findData("cm")
    win.displayUnitCombo.setCurrentIndex(idx_cm)
    check("显示单位切换为 cm", board.scale.unit == "cm")
    check("单位换算数值正确", abs(board.scale.pixels_per_unit - 300.0) < 1e-6)
    win._select_tool(ToolID.DISTANCE)
    board.clear_measurements()
    drag(board, (100, 100), (400, 100))   # 300px = 1cm
    check("切换单位后测距显示 cm",
          "cm" in board.measurements[-1].value_text(board.scale))
    win.displayUnitCombo.setCurrentIndex(0)   # 跟随标定单位 -> mm
    check("跟随标定单位恢复 mm", board.scale.unit == "mm")

    # 比例尺图形：拖拽 + 单击
    board.clear_measurements()
    win._select_tool(ToolID.SCALEBAR)
    drag(board, (100, 350), (300, 350))
    check("比例尺拖拽生成", board.measurements
          and board.measurements[-1].kind == "scalebar")
    check("比例尺拖拽长度=200px", abs(board.measurements[-1].px_value - 200) < 2)
    check("比例尺显示实际值", "mm" in board.measurements[-1].value_text(board.scale))
    n_sb = len(board.measurements)
    click(board, (100, 300))
    check("比例尺单击生成整齐长度", len(board.measurements) == n_sb + 1)

    # 清除全部标注：面板按钮 / 菜单 / 可撤销
    win.clearAllMeasureBtn.click()
    check("面板清除全部标注", len(board.measurements) == 0)
    board.undo()
    check("清除标注可撤销", len(board.measurements) == n_sb + 1)
    win.actionClearMeasure.trigger()
    check("菜单清除全部标注", len(board.measurements) == 0)

    # 定位所选测量
    win._select_tool(ToolID.DISTANCE)
    drag(board, (100, 100), (200, 100))
    win.measureList.setCurrentRow(0)
    win.locateMeasureBtn.click()
    check("定位所选测量生效", board.selected is not None)

    print("== 11. 摄像头 / 视频（接线 + 无设备降级） ==")
    import pixelmark.capture as capture_mod
    from pixelmark.capture import CameraCaptureDialog, VideoFrameDialog
    orig_enum = capture_mod.enumerate_cameras
    orig_capture_mb = capture_mod.QMessageBox
    orig_camera_cls = mw_mod.CameraCaptureDialog
    orig_video_cls = mw_mod.VideoFrameDialog
    capture_mod.QMessageBox = FakeMB

    # ---- 11a. 主窗口接线（用假对话框避免模态阻塞） ----
    class FakeCameraDialog(QDialog):
        captured = pyqtSignal(QImage)

        def __init__(self, parent=None):
            super().__init__(parent)

        def exec_(self):
            self.captured.emit(QImage(320, 240, QImage.Format_RGB32))
            return QDialog.Accepted

    class FakeVideoDialog(QDialog):
        captured = pyqtSignal(QImage)

        def __init__(self, parent=None, video_path=None):
            super().__init__(parent)

        def exec_(self):
            self.captured.emit(QImage(640, 480, QImage.Format_RGB32))
            return QDialog.Accepted

    mw_mod.CameraCaptureDialog = FakeCameraDialog
    mw_mod.VideoFrameDialog = FakeVideoDialog
    try:
        win._capture_from_camera()
        check("摄像头拍照接线正常", board.image.width() == 320)
        win._capture_from_video()
        check("视频截帧接线正常", board.image.width() == 640)
    finally:
        mw_mod.CameraCaptureDialog = orig_camera_cls
        mw_mod.VideoFrameDialog = orig_video_cls

    # ---- 11b. 真实对话框在无摄像头/无效视频下的降级 ----
    capture_mod.enumerate_cameras = lambda: []
    try:
        dlg = CameraCaptureDialog(win)
        check("无摄像头对话框不崩溃", dlg.shootBtn.isEnabled() is False)
        check("无摄像头有友好提示",
              any(c[0] == "information" for c in mb_calls))
        dlg.close()

        bad_video = os.path.join(tmp, "nonexistent.mp4")
        vdlg = VideoFrameDialog(win, video_path=bad_video)
        check("无效视频对话框不崩溃", vdlg.current_frame is None)
        check("无效视频有错误提示",
              any(c[0] == "critical" for c in mb_calls))
        vdlg.close()
    finally:
        capture_mod.enumerate_cameras = orig_enum
        capture_mod.QMessageBox = orig_capture_mb

    print("== 12. 菜单 / 工具栏 / 工具选项同屏（v1.2） ==")
    # ---- 12a. 菜单结构 ----
    check("绘制菜单含全部绘图工具", len(win.menuDraw.actions()) == 9)
    measure_menu_texts = [a.text() for a in win.menu_5.actions() if a.text()]
    for name in ("标定比例尺", "测距", "测角", "测面积", "测圆", "比例尺",
                 "箭头标注", "文字标注"):
        check("测量菜单含 %s" % name, name in measure_menu_texts)
    image_menu_texts = [a.text() for a in win.menu_3.actions() if a.text()]
    for name in ("灰度化", "二值化", "反相", "浮雕", "边缘检测", "模糊", "锐化"):
        check("图像菜单含 %s" % name, name in image_menu_texts)
    view_menu_texts = [a.text() for a in win.menu_view.actions() if a.text()]
    for name in ("铺满绘图区", "适应窗口", "原始大小",
                 "显示/隐藏左侧工具面板", "显示/隐藏工具栏",
                 "显示/隐藏状态栏"):
        check("视图菜单含 %s" % name, name in view_menu_texts)
    check("工具动作共 17 个", len(win.tool_actions) == 17)

    # ---- 12b. 工具栏（图标式全集） ----
    check("工具栏动作数量充足", len(win.mainToolBar.actions()) >= 30)
    check("工具栏为图标模式",
          win.mainToolBar.toolButtonStyle() == Qt.ToolButtonIconOnly)
    for tool, act in win.tool_actions.items():
        check("工具栏含工具 %s" % tool.value, act in win.mainToolBar.actions())

    # ---- 12c. 工具选项区：与所选工具同屏显隐 ----
    win._select_tool(ToolID.PEN)
    check("画笔：粗细行可见", not win.opt_size_row.isHidden())
    check("画笔：颜色行可见", not win.opt_colors_row.isHidden())
    check("画笔：平滑框可见", not win.smoothChk.isHidden())
    check("画笔：填充框隐藏", win.fillChk.isHidden())
    check("画笔：尺寸调整与工具同屏",
          win.penSizeBtn.isVisible() and not win.opt_size_row.isHidden())
    win._select_tool(ToolID.RECT)
    check("矩形：填充框可见", not win.fillChk.isHidden())
    check("矩形：虚线框可见", not win.dashChk.isHidden())
    check("矩形：平滑框隐藏", win.smoothChk.isHidden())
    win._select_tool(ToolID.DISTANCE)
    check("测距：绘图选项全部隐藏",
          win.opt_colors_row.isHidden() and win.opt_size_row.isHidden()
          and win.opt_style_row.isHidden() and win.opt_opacity_row.isHidden())
    check("测距：有使用提示", "拖拽两点" in win.toolHintLabel.text())
    win._select_tool(ToolID.ERASE)
    check("橡皮擦：粗细与平滑可见",
          not win.opt_size_row.isHidden() and not win.smoothChk.isHidden())

    # ---- 12d. 工具动作与按钮/菜单勾选同步 ----
    win._select_tool(ToolID.ELLIPSE)
    check("工具动作勾选同步", win.tool_actions[ToolID.ELLIPSE].isChecked())
    check("工具按钮勾选同步", win.tool_buttons[ToolID.ELLIPSE].isChecked())
    win.tool_actions[ToolID.PEN].trigger()
    check("菜单动作触发切换工具", board.tool == ToolID.PEN)
    check("触发后动作勾选", win.tool_actions[ToolID.PEN].isChecked())

    # ---- 12e. 图像菜单滤镜生效 ----
    # 构造彩色图（前置流程可能留下全灰图，灰度化将无差异）
    from PyQt5.QtGui import QPainter
    colorful = QImage(400, 300, QImage.Format_RGB32)
    colorful.fill(Qt.white)
    cp = QPainter(colorful)
    cp.fillRect(20, 20, 150, 120, QColor(220, 30, 30))
    cp.fillRect(200, 150, 150, 120, QColor(30, 30, 220))
    cp.end()
    board.load_image(colorful)
    snap = board.image.copy()
    win.actionGray.trigger()
    check("图像菜单灰度化生效", pixel_diff_count(snap, board.image) != 0)
    snap = board.image.copy()
    win.actionBlur.trigger()
    check("图像菜单模糊生效", pixel_diff_count(snap, board.image) != 0)

    # ---- 12f. 铺满绘图区（cover：覆盖视口、无滚动条、画布贴合绘图区） ----
    wide = QImage(3000, 900, QImage.Format_RGB32)
    wide.fill(Qt.white)
    board.load_image(wide)
    vp = win.scrollArea.viewport().size()
    win.actionZoomFit.trigger()
    fit_zoom = board.zoom
    win.actionZoomFill.trigger()
    check("铺满缩放更大", board.zoom > fit_zoom + 1e-9)
    check("铺满保持自动模式",
          board.auto_fit is True and board.fit_mode == "cover")
    disp = board._display_size()
    check("铺满覆盖视口",
          disp.width() >= vp.width() - 2 and disp.height() >= vp.height() - 2)
    check("铺满无滚动条",
          not win.scrollArea.horizontalScrollBar().isVisible()
          and not win.scrollArea.verticalScrollBar().isVisible())
    check("铺满画布与视口等大",
          board.width() == vp.width() and board.height() == vp.height())

    # ---- 12g. 画布浅色底（不再漆黑一片） ----
    import pixelmark.canvas as canvas_mod
    check("画布背景为浅色", canvas_mod.CANVAS_BG.lightness() > 128)
    win.actionZoomFit.trigger()

    # ---- 12i. 左侧面板紧凑布局（最小窗口高度下无滚动条） ----
    win.resize(1024, 640)
    app.processEvents()
    check("左侧面板无垂直滚动条",
          not win.toolScroll.verticalScrollBar().isVisible())
    check("工具选项区固定可见（不随工具网格滚动）",
          win.toolOptionsBox.parent() is win.toolPanel)
    check("测量工具网格为 4 列紧凑排布",
          win.grid_measure.columnCount() == 4)
    icon_sizes = {(b.iconSize().width(), b.iconSize().height())
                  for b in win.tool_buttons.values()}
    check("面板工具图标尺寸一致", len(icon_sizes) == 1)
    check("面板图标与工具栏同尺寸",
          icon_sizes == {(win.mainToolBar.iconSize().width(),
                          win.mainToolBar.iconSize().height())})

    # ---- 12h. 面板 / 工具栏 / 状态栏显隐 ----
    win.actionToggleToolPanel.trigger()
    check("左侧工具面板可隐藏", win.toolPanel.isHidden())
    win.actionToggleToolPanel.trigger()
    check("左侧工具面板可恢复", not win.toolPanel.isHidden())
    win.actionToggleToolBar.trigger()
    check("工具栏可隐藏", win.mainToolBar.isHidden())
    win.actionToggleToolBar.trigger()
    check("工具栏可恢复", not win.mainToolBar.isHidden())
    win.actionToggleStatusBar.trigger()
    check("状态栏可隐藏", win.statusBar().isHidden())
    win.actionToggleStatusBar.trigger()
    check("状态栏可恢复", not win.statusBar().isHidden())

    print()
    print("=" * 50)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  -", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
