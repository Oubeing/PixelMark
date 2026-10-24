# -*- coding: utf-8 -*-
"""CanvasWidget —— 画布控件（QLabel 子类）。

职责：
- 承载提交后的图像（``self.image``）与双缓冲预览（``self.preview``）；
- 全部鼠标交互（绘图工具 / 测量工具 / 取色 / 标注拖动调整）；
- 统一撤销 / 重做（图像操作与测量操作交错也能正确回退）；
- 测量标注叠加层的渲染、选择、命中测试与拖动调整；
- 比例尺状态维护；
- 视图变换：缩放（zoom）、铺满绘图区（cover）、适应窗口（contain）、坐标映射。

设计要点：
- 事件直接发生在画布上，坐标为控件本地坐标，无需换算、不会越界错乱；
- ``event.buttons() & Qt.LeftButton`` 正确判断按键；
- 油漆桶只在按下时执行一次（移动中反复全图泛洪会卡死）；
- 形状绘制期间用预览层（双缓冲），松开才提交。

视图模型：
- 图像始终居中绘制，显示尺寸 = 图像尺寸 × ``zoom``；
- **铺满（cover，默认）**：缩放至图像覆盖整个视口，居中裁剪边缘，
  画布控件与视口等大——不出现滚动条、不留边缘空白；
- **适应窗口（contain）**：缩放至整图完整可见，居中 letterbox（小图不放大）；
- **手动缩放**：控件尺寸 = 显示尺寸（``setMinimumSize`` 驱动，
  外层 QScrollArea 自然出现滚动条）；
- 所有鼠标坐标经 ``map_to_image`` 除以 zoom 换算回图像坐标，
  绘图与测量逻辑全部保持在图像坐标系中，与缩放无关。

标注调整模型：
- 左键命中标注即选中；按住拖动可**整体移动**，拖动控制点（白色小方框）
  可**调整端点 / 大小 / 角度**；双击文字类标注可编辑文字；
- 调整通过"替换为新测量对象"实现，撤销快照始终持有原对象，
  因此拖动可正确撤销 / 重做。
"""

import math

from PyQt5.QtCore import (QPoint, QPointF, QRect, QRectF, QSize, Qt,
                          pyqtSignal)
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QLabel

from .tools import DRAG_TOOLS, FREEHAND_TOOLS, MEASURE_TOOLS, MULTI_CLICK_TOOLS, ToolID
from .measurement import (SELECT_COLOR, Measurement, Scale, distance, fmt_area,
                          fmt_angle, fmt_length, make_angle, make_arrow,
                          make_calibrate, make_circle, make_distance,
                          make_rect_area, make_scalebar, make_text,
                          nice_scalebar_pixels, replace)
from .util import imageutil as IU
from .util.errors import ImageSaveError
from .util.logging import get_logger

logger = get_logger("canvas")

MAX_HISTORY = 40
HISTORY_BYTE_BUDGET = 256 * 1024 * 1024  # 撤销栈内存预算 256MB

MIN_ZOOM = 0.02
MAX_ZOOM = 32.0
ZOOM_STEP = 1.25
FIT_MAX_ZOOM = 1.0   # 适应窗口时不放大小图（保持像素清晰）
MAX_QSize = QSize(16777215, 16777215)   # Qt 最大控件尺寸

# 自动适应模式：cover=铺满绘图区（裁剪边缘、无滚动条）；
# contain=适应窗口（整图可见、letterbox 居中）
FIT_COVER = "cover"
FIT_CONTAIN = "contain"

CANVAS_BG = QColor(232, 234, 238)      # 图像外区域（浅灰，避免漆黑一片）
CANVAS_BORDER = QColor(150, 156, 166)  # 图像边框（勾出画布边界）
CANVAS_EMPTY_TEXT = QColor(120, 126, 134)


class CanvasWidget(QLabel):
    """画布控件：图像 + 测量叠加层 + 工具交互 + 视图缩放。"""

    # ---- 对外信号 ----
    statusHint = pyqtSignal(str)        # 状态栏提示
    coordChanged = pyqtSignal(int, int)  # 鼠标图像坐标
    scaleChanged = pyqtSignal(str)      # 比例尺描述变化
    measurementsChanged = pyqtSignal()  # 测量列表变化
    colorPicked = pyqtSignal(QColor)    # 取色器取到的颜色
    imageChanged = pyqtSignal()         # 图像内容变化（用于标题脏标记）
    zoomChanged = pyqtSignal(float)     # 缩放比例变化
    calibrateRequested = pyqtSignal(QPoint, QPoint, float)  # 比例尺标定请求

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # ---- 图像状态 ----
        self.image = QImage(658, 413, QImage.Format_RGB32)
        self.image.fill(Qt.white)
        self.ori_image = self.image.copy()   # 打开时的原图（"还原"用）
        self.preview = None                  # 双缓冲预览层

        # ---- 历史（统一动作栈：图像与测量交错） ----
        self._history = []   # [(kind, payload)] kind: 'image' | 'measure'
        self._future = []

        # ---- 测量 ----
        self.measurements = []
        self.selected = None
        self.scale = Scale()

        # ---- 工具与画笔状态 ----
        self.tool = ToolID.PEN
        self.pen_color = Qt.black
        self.back_color = Qt.white
        self.pen_size = 2
        self.fill_shapes = False
        self.dashed = False
        self.smooth = True
        self.opacity = 1.0

        # ---- 视图 ----
        self.zoom = 1.0
        self.auto_fit = True        # 视口变化时自动调整缩放
        self.fit_mode = FIT_COVER   # 自动模式：默认铺满绘图区（无滚动条）

        # ---- 交互状态 ----
        self._drawing = False
        self._button = Qt.LeftButton
        self._start = QPoint()
        self._last = QPoint()
        self._last_mid = QPointF()
        self._pending = []          # 多次点击工具的点序列
        self._active_measure = None  # 正在拖拽中的测量预览
        self._panning = False        # 中键平移
        self._pan_origin = QPoint()
        self._measure_drag = None    # 标注拖动状态（见 _hit_annotation）
        self._tool_cursor = Qt.CrossCursor   # 当前工具光标（悬停标注时临时替换）

        self._update_size()

    # ------------------------------------------------------------------
    # 视图变换：缩放 / 适应窗口 / 坐标映射
    # ------------------------------------------------------------------
    def _clamp_zoom(self, z):
        return max(MIN_ZOOM, min(MAX_ZOOM, float(z)))

    def set_zoom(self, zoom, auto_fit=False):
        """设置缩放比例（auto_fit=True 表示保持自动适应模式）。"""
        z = self._clamp_zoom(zoom)
        changed = abs(z - self.zoom) > 1e-9 or auto_fit != self.auto_fit
        self.zoom = z
        self.auto_fit = auto_fit
        self._update_size()
        self.update()
        if changed:
            self.zoomChanged.emit(z)

    def zoom_by(self, factor):
        self.set_zoom(self.zoom * factor)

    def zoom_in(self):
        self.set_zoom(self.zoom * ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self.zoom / ZOOM_STEP)

    def zoom_reset(self):
        self.set_zoom(1.0)

    def zoom_fit(self):
        """适应窗口：按视口大小计算缩放（整图可见，小图不放大）。"""
        self.auto_fit = True
        self.fit_mode = FIT_CONTAIN
        self._apply_fit()

    def zoom_fill(self):
        """铺满绘图区：缩放至图像覆盖整个视口，居中裁剪边缘。

        画布控件与视口等大，因此**不出现滚动条、不留边缘空白**；
        被裁剪的边缘可切换「适应窗口」或缩小查看。窗口最大化 /
        还原时自动重新计算，始终保持铺满。
        """
        if self.image.isNull():
            self.statusHint.emit("画布为空，无法铺满绘图区")
            return
        self.auto_fit = True
        self.fit_mode = FIT_COVER
        self._apply_fit()
        self.statusHint.emit("已铺满绘图区（%d%%，边缘自动裁剪，无滚动条）"
                             % round(self.zoom_percent()))

    def _viewport_size(self):
        """向外查找外层 QScrollArea 的视口尺寸。"""
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "viewport") and hasattr(parent, "horizontalScrollBar"):
                try:
                    return parent.viewport().size()
                except Exception:  # noqa: BLE001
                    return None
            parent = parent.parent()
        return None

    def _apply_fit(self):
        """按当前自动模式（cover/contain）计算缩放。"""
        if self.image.isNull():
            return
        vp = self._viewport_size()
        if vp is None or vp.width() <= 0 or vp.height() <= 0:
            return
        if self.fit_mode == FIT_COVER:
            # 铺满：取较大比例，覆盖视口（边缘裁剪），不放上限
            z = max(vp.width() / float(self.image.width()),
                    vp.height() / float(self.image.height()))
        else:
            # 适应窗口：取较小比例，整图可见，且不放大小图
            z = min(vp.width() / float(self.image.width()),
                    vp.height() / float(self.image.height()))
            z = min(z, FIT_MAX_ZOOM)
        self.zoom = self._clamp_zoom(z)
        self._update_size()
        self.update()
        self.zoomChanged.emit(self.zoom)

    def refit_if_auto(self):
        """自动适应模式下按当前视口重新计算缩放（供窗口 resize 调用）。"""
        if self.auto_fit:
            self._apply_fit()

    def zoom_percent(self):
        return self.zoom * 100.0

    def _display_size(self):
        if self.image.isNull():
            return QSize()
        return QSize(int(math.ceil(self.image.width() * self.zoom)),
                     int(math.ceil(self.image.height() * self.zoom)))

    def _image_rect(self):
        """图像在控件中的绘制区域（始终居中，允许负偏移——铺满裁剪）。"""
        if self.image.isNull():
            return QRectF()
        d = self._display_size()
        x = (self.width() - d.width()) / 2.0
        y = (self.height() - d.height()) / 2.0
        return QRectF(x, y, d.width(), d.height())

    def map_to_image(self, pos):
        """控件坐标 -> 图像坐标（QPointF，可能越界，由调用方裁剪）。"""
        if self.image.isNull() or self.zoom <= 0:
            return QPointF()
        r = self._image_rect()
        return QPointF((pos.x() - r.x()) / self.zoom,
                       (pos.y() - r.y()) / self.zoom)

    def _event_pos(self, event):
        """事件坐标 -> 裁剪到图像范围内的 QPoint。"""
        return self._clamp(self.map_to_image(event.pos()))

    def _widget_pos_in_image(self, pos):
        f = self.map_to_image(pos)
        return (0 <= f.x() < self.image.width()
                and 0 <= f.y() < self.image.height())

    # ------------------------------------------------------------------
    # 尺寸与刷新
    # ------------------------------------------------------------------
    def _update_size(self):
        if self.image.isNull():
            return
        d = self._display_size()
        if self.auto_fit:
            vp = self._viewport_size()
            if vp is not None and vp.width() > 0 and vp.height() > 0:
                if self.fit_mode == FIT_COVER:
                    # 铺满：控件与视口等大。QScrollArea 布局不会把子控件
                    # 收缩到旧的最小尺寸以下（实验验证），用固定尺寸最可靠，
                    # 保证不出现滚动条、不留边缘空白。
                    self.setFixedSize(vp)
                else:
                    # 适应窗口：解除固定尺寸，最小尺寸钳制到视口
                    # （避免取整误差产生 1px 滚动条）
                    self._unfix_size()
                    self.setMinimumSize(min(d.width(), vp.width()),
                                        min(d.height(), vp.height()))
                return
        # 手动缩放：解除固定，最小尺寸 = 显示尺寸（驱动外层滚动条）
        self._unfix_size()
        self.setMinimumSize(d)

    def _unfix_size(self):
        """解除 cover 模式的固定尺寸限制。"""
        self.setMinimumSize(0, 0)
        self.setMaximumSize(MAX_QSize)

    def refresh(self):
        self._update_size()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 图像外区域：浅灰底 + 居中 letterbox，不再留漆黑边缘
        painter.fillRect(self.rect(), CANVAS_BG)
        base = self.preview if self.preview is not None else self.image
        if base.isNull():
            painter.setPen(CANVAS_EMPTY_TEXT)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "画布为空\n（文件 → 新建 / 打开图像，或点击工具栏）")
            painter.end()
            return
        target = self._image_rect()
        painter.drawPixmap(target, QPixmap.fromImage(base),
                           QRectF(base.rect()))
        # 图像边框：明确勾出画布边界，与浅灰背景区分
        painter.setPen(QPen(CANVAS_BORDER, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target.adjusted(0.5, 0.5, -0.5, -0.5))
        # 测量叠加层：与图像共用同一变换
        painter.save()
        painter.translate(target.topLeft())
        painter.scale(self.zoom, self.zoom)
        for m in self.measurements:
            m.draw(painter, self.scale, selected=(m is self.selected), font=self.font())
        if self._active_measure is not None:
            self._active_measure.draw(painter, self.scale, font=self.font())
        painter.restore()
        # 选中标注的控制点手柄（控件坐标，屏幕尺寸恒定）
        if self.selected is not None and any(m is self.selected
                                             for m in self.measurements):
            self._draw_handles(painter, self.selected, target)
        painter.end()

    def wheelEvent(self, event):
        """Ctrl+滚轮缩放；普通滚轮交给外层滚动区。"""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # 撤销 / 重做
    # ------------------------------------------------------------------
    def _snapshot(self, kind):
        if kind == "image":
            return self.image.copy()
        return list(self.measurements)

    def _payload_bytes(self, kind, payload):
        if kind == "image":
            return payload.byteCount()
        return 0

    def begin_action(self, kind):
        """在任何修改前调用：把当前状态压入撤销栈并清空重做栈。"""
        self._history.append((kind, self._snapshot(kind)))
        total = 0
        while len(self._history) > MAX_HISTORY:
            self._history.pop(0)
        # 超出内存预算时从最旧开始丢弃
        sizes = [self._payload_bytes(k, p) for k, p in self._history]
        total = sum(sizes)
        while total > HISTORY_BYTE_BUDGET and len(self._history) > 1:
            k, p = self._history.pop(0)
            total -= self._payload_bytes(k, p)
        self._future.clear()

    def undo(self):
        if not self._history:
            self.statusHint.emit("没有可撤销的操作")
            return
        kind, payload = self._history.pop()
        current = self._snapshot(kind)
        if kind == "image":
            self.image = payload
            self.refit_if_auto()
            self._update_size()
        else:
            self.measurements = payload
        self._future.append((kind, current))
        self.imageChanged.emit()
        self.measurementsChanged.emit()
        self.update()
        self.statusHint.emit("已撤销")

    def redo(self):
        if not self._future:
            self.statusHint.emit("没有可重做的操作")
            return
        kind, payload = self._future.pop()
        current = self._snapshot(kind)
        if kind == "image":
            self.image = payload
            self.refit_if_auto()
            self._update_size()
        else:
            self.measurements = payload
        self._history.append((kind, current))
        self.imageChanged.emit()
        self.measurementsChanged.emit()
        self.update()
        self.statusHint.emit("已重做")

    def can_undo(self):
        return bool(self._history)

    def can_redo(self):
        return bool(self._future)

    # ------------------------------------------------------------------
    # 图像操作（供窗口菜单调用）
    # ------------------------------------------------------------------
    def new_image(self, width, height, background=None):
        self.begin_action("image")
        self.image = QImage(max(1, int(width)), max(1, int(height)), QImage.Format_RGB32)
        self.image.fill(background if background is not None else self.back_color)
        self.ori_image = self.image.copy()
        self.measurements = []
        self.selected = None
        self._pending = []
        self._active_measure = None
        self.preview = None
        self.refit_if_auto()
        self.refresh()
        self.measurementsChanged.emit()
        self.imageChanged.emit()

    def load_image(self, image):
        if image is None or image.isNull():
            raise ImageSaveError("无法加载图像：数据为空")
        self.begin_action("image")
        self.image = image.convertToFormat(QImage.Format_RGB32) \
            if image.hasAlphaChannel() else image
        self.ori_image = self.image.copy()
        self.measurements = []
        self.selected = None
        self.refit_if_auto()   # 导入后自动适应窗口，保证完整可见
        self.refresh()
        self.measurementsChanged.emit()
        self.imageChanged.emit()

    def clear_all(self):
        """清空画布（填充背景色）。"""
        self.begin_action("image")
        self.image.fill(self.back_color)
        self.refresh()
        self.imageChanged.emit()

    def restore_original(self):
        """还原到打开时的图像。"""
        self.begin_action("image")
        self.image = self.ori_image.copy()
        self.refit_if_auto()
        self.refresh()
        self.imageChanged.emit()

    def transform_image(self, func):
        """旋转/翻转等整体变换（func: QImage -> QImage）。"""
        self.begin_action("image")
        try:
            self.image = func(self.image)
        except Exception as exc:  # noqa: BLE001
            logger.exception("图像变换失败")
            self.statusHint.emit("图像变换失败: %s" % exc)
            self._history.pop()
            return False
        self.refit_if_auto()
        self.refresh()
        self.imageChanged.emit()
        return True

    def apply_filter(self, func, name="滤镜"):
        """应用图像滤镜（func: QImage -> QImage），带错误处理。"""
        if self.image.isNull():
            self.statusHint.emit("画布为空，无法应用%s" % name)
            return False
        self.begin_action("image")
        try:
            result = func(self.image)
            if result is None or result.isNull():
                raise ImageSaveError("%s返回了空图像" % name)
            self.image = result
        except Exception as exc:  # noqa: BLE001
            logger.exception("应用%s失败", name)
            self.statusHint.emit("%s失败: %s" % (name, exc))
            self._history.pop()
            self.refresh()
            return False
        self.refresh()
        self.imageChanged.emit()
        self.statusHint.emit("已应用%s" % name)
        return True

    def flattened_image(self, with_measurements=True):
        """返回用于保存的图像（可选叠加测量标注）。"""
        if not with_measurements or not self.measurements:
            return self.image.copy()
        out = self.image.copy()
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for m in self.measurements:
            m.draw(painter, self.scale, font=self.font())
        painter.end()
        return out

    # ------------------------------------------------------------------
    # 测量操作
    # ------------------------------------------------------------------
    def clear_measurements(self):
        if not self.measurements:
            self.statusHint.emit("当前没有测量标注")
            return
        self.begin_action("measure")
        self.measurements = []
        self.selected = None
        self.measurementsChanged.emit()
        self.update()
        self.statusHint.emit("已清除全部测量标注")

    def delete_selected(self):
        if self.selected is None:
            self.statusHint.emit("请先在测量列表中选择要删除的标注")
            return
        self.begin_action("measure")
        self.measurements = [m for m in self.measurements if m is not self.selected]
        self.selected = None
        self.measurementsChanged.emit()
        self.update()
        self.statusHint.emit("已删除所选测量标注")

    def locate_measurement(self, measurement):
        """在视口中定位某个测量标注（退出自动模式并滚动到其位置）。"""
        if measurement is None:
            return
        bounds = measurement.bounds()
        if bounds.isNull():
            return
        # 自动模式（铺满/适应）下没有滚动条，先退出手动缩放再滚动
        self.set_zoom(max(self.zoom, 1.0), auto_fit=False)
        center_img = bounds.center()
        target = QPoint(int(center_img.x() * self.zoom),
                        int(center_img.y() * self.zoom))
        self.scroll_to_image_point(target)
        self.selected = measurement
        self.update()

    def scroll_to_image_point(self, img_point):
        """把图像坐标点滚动到可见区域（操作外层 QScrollArea）。"""
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "horizontalScrollBar"):
                hbar = parent.horizontalScrollBar()
                vbar = parent.verticalScrollBar()
                hbar.setValue(int(img_point.x() - hbar.pageStep() / 2))
                vbar.setValue(int(img_point.y() - vbar.pageStep() / 2))
                return True
            parent = parent.parent()
        return False

    def select_at(self, point, slack=6.0):
        """命中测试：从最上层（列表末尾）往下找。point 为图像坐标。"""
        for m in reversed(self.measurements):
            if m.hit_test(QPointF(point), slack=slack):
                return m
        return None

    def set_scale(self, scale):
        self.scale = scale
        self.scaleChanged.emit(scale.describe())
        self.measurementsChanged.emit()
        self.update()

    def clear_scale(self):
        self.set_scale(Scale())

    def add_measurement(self, measurement):
        self.begin_action("measure")
        self.measurements.append(measurement)
        self.measurementsChanged.emit()
        self.update()

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def _clamp(self, point):
        if self.image.isNull():
            return QPoint(0, 0)
        # 四舍五入到最近像素：小数缩放下避免系统性偏差（截断会让
        # 100px 的线段测出 101px）
        x = int(round(max(0, min(self.image.width() - 1, point.x()))))
        y = int(round(max(0, min(self.image.height() - 1, point.y()))))
        return QPoint(x, y)

    def _in_image(self, point):
        return (0 <= point.x() < self.image.width()
                and 0 <= point.y() < self.image.height())

    # ------------------------------------------------------------------
    # 标注命中与拖动调整
    # ------------------------------------------------------------------
    def _hit_slack(self):
        """命中容差（图像坐标）：折算后约为屏幕上 7px。"""
        return 7.0 / max(self.zoom, 0.05)

    def _hit_annotation(self, img_pt):
        """图像坐标处的标注命中。

        优先已选中标注的控制点（返回 handle 序号），其次任意标注本体
        （自上而下）。返回 (measurement, handle|None) 或 None。
        """
        slack = self._hit_slack()
        if self.selected is not None:
            for i, p in enumerate(self.selected.points):
                if distance(p, img_pt) <= slack:
                    return self.selected, i
        m = self.select_at(img_pt, slack=slack)
        if m is not None:
            return m, None
        return None

    def _drag_annotation(self, widget_pos):
        """拖动标注：整体移动或单控制点调整（首次实际移动才入撤销栈）。"""
        drag = self._measure_drag
        if drag is None:
            return
        m = drag["m"]
        img_f = self.map_to_image(widget_pos)
        if not drag["moved"]:
            # 单击（无位移）不产生撤销步；首次移动时快照的是原对象
            self.begin_action("measure")
            drag["moved"] = True
        dx = img_f.x() - drag["start"].x()
        dy = img_f.y() - drag["start"].y()
        if drag["handle"] is None:
            new_m = m.translated(dx, dy)
        else:
            p = m.points[drag["handle"]]
            new_m = m.with_point(drag["handle"], QPointF(p.x() + dx, p.y() + dy))
        # 用新对象替换旧对象：撤销快照持有的是原对象，可正确回退
        for i, x in enumerate(self.measurements):
            if x is m:
                self.measurements[i] = new_m
                break
        self.selected = new_m
        drag["m"] = new_m
        self.update()

    def _end_annotation_drag(self):
        drag = self._measure_drag
        self._measure_drag = None
        self.unsetCursor()
        if drag is not None and drag["moved"]:
            self.measurementsChanged.emit()
            self.statusHint.emit("标注已调整：%s" % drag["m"].title(self.scale))
        self.update()

    def cancel_interaction(self):
        """取消一切进行中的交互（拖拽标注 / 多点 / 预览），供 Esc 调用。"""
        had = (self._measure_drag is not None or bool(self._pending)
               or self._active_measure is not None)
        self._measure_drag = None
        self._pending = []
        self._active_measure = None
        if self._drawing:
            self._drawing = False
        self.unsetCursor()
        if had:
            self.statusHint.emit("已取消当前操作")
        self.update()

    def _edit_annotation_text(self, m):
        """双击文字类标注：编辑其文字内容。"""
        from .dialogs import TextInputDialog
        dlg = TextInputDialog(self, title="编辑标注", placeholder="输入标注文字（可留空）")
        dlg.text_edit.setPlainText(m.label or "")
        if not dlg.exec_():
            self.statusHint.emit("已取消编辑")
            return
        text, _ = dlg.values()
        self.begin_action("measure")
        new_m = replace(m, label=text.strip())
        for i, x in enumerate(self.measurements):
            if x is m:
                self.measurements[i] = new_m
                break
        self.selected = new_m
        self.measurementsChanged.emit()
        self.update()
        self.statusHint.emit("标注文字已更新")

    def _draw_handles(self, painter, m, image_rect):
        """选中标注的控制点手柄：白色小方框 + 蓝边（控件坐标，尺寸恒定）。"""
        painter.save()
        for p in m.points:
            c = QPointF(image_rect.x() + p.x() * self.zoom,
                        image_rect.y() + p.y() * self.zoom)
            painter.setPen(QPen(SELECT_COLOR, 1.5))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRect(QRectF(c.x() - 4, c.y() - 4, 8, 8))
        painter.restore()

    def set_tool_cursor(self, cursor):
        """设置当前工具的光标（悬停标注时临时替换，移开后恢复）。"""
        self._tool_cursor = cursor
        if self._measure_drag is None:
            self.setCursor(cursor)

    def _update_hover_cursor(self, widget_pos):
        """悬停反馈：标注控制点上用十字光标，标注本体上用移动光标。"""
        if self._drawing or self._pending or self._panning:
            return
        hit = self._hit_annotation(self.map_to_image(widget_pos))
        if hit is not None:
            self.setCursor(Qt.CrossCursor if hit[1] is not None else Qt.SizeAllCursor)
        else:
            self.setCursor(self._tool_cursor)

    def mousePressEvent(self, event):
        if self.image.isNull():
            return
        # 中键平移（放大后快速导航）
        if event.button() == Qt.MidButton:
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # 左键命中标注：选中并进入拖动调整（优先于绘图/测量工具）
        if event.button() == Qt.LeftButton:
            img_pt = self.map_to_image(event.pos())
            hit = self._hit_annotation(img_pt)
            if hit is not None:
                m, handle = hit
                self.selected = m
                self._measure_drag = {"m": m, "handle": handle,
                                      "start": img_pt, "moved": False}
                self.setCursor(Qt.SizeAllCursor if handle is None else Qt.CrossCursor)
                self.statusHint.emit(
                    "已选中标注，拖动可整体移动" if handle is None
                    else "已选中标注，拖动控制点可调整形状")
                self.update()
                event.accept()
                return
            if self.selected is not None:
                self.selected = None   # 点空白处取消选中
                self.update()
        pos = self._event_pos(event)
        self._button = event.button()
        inside = self._widget_pos_in_image(event.pos())

        # 右键随时取消进行中的多点操作
        if event.button() == Qt.RightButton:
            if self._pending or self._active_measure is not None:
                self._pending = []
                self._active_measure = None
                self.statusHint.emit("已取消当前操作")
                self.update()
                return

        tool = self.tool

        # 取色器
        if tool == ToolID.PICKER:
            if inside:
                color = QColor(self.image.pixel(pos))
                self.pen_color = color
                self.colorPicked.emit(color)
                self.statusHint.emit("取色 #%02X%02X%02X" % (color.red(), color.green(), color.blue()))
            return

        # 文字类：单击弹窗输入
        if tool in (ToolID.TEXT, ToolID.ANNOT_TEXT):
            if inside:
                self._request_text(pos)
            return

        # 多次点击（测角）
        if tool in MULTI_CLICK_TOOLS:
            if not inside:
                return
            self._pending.append(pos)
            if len(self._pending) == 3:
                m = make_angle(self._pending[0], self._pending[1], self._pending[2])
                self.add_measurement(m)
                self._pending = []
                self._active_measure = None
                self.statusHint.emit("角度: %s" % fmt_angle(m.px_value))
            else:
                self.statusHint.emit("测角：还需点击 %d 个点（右键取消）" % (3 - len(self._pending)))
            self.update()
            return

        # 拖拽类
        if tool in DRAG_TOOLS:
            self._drawing = True
            self._start = pos
            self._last = pos
            # 形状类提交时直接绘制到图像，需要在按下时快照；
            # 测量类由 add_measurement 统一入栈，避免重复条目
            if tool not in MEASURE_TOOLS:
                self.begin_action("image")
            return

        # 自由绘制 / 油漆桶 / 比例尺图形（单击或拖拽）
        if tool in FREEHAND_TOOLS:
            self._drawing = True
            self._start = pos
            self._last = pos
            self._last_mid = QPointF(pos)
            self.begin_action("image")
            self._draw_freehand(pos)
            # 平滑模式下首段是退化路径（不落墨），补一个点保证单击有痕迹
            if self.smooth:
                dot_color = self.back_color if self.tool == ToolID.ERASE \
                    else self._effective_color()
                self._draw_dot(pos, dot_color)
        elif tool == ToolID.BUCKET:
            if inside:
                self.begin_action("image")
                self._apply_bucket(pos)
        elif tool == ToolID.SCALEBAR:
            if inside:
                # 拖拽定义长度；单击（几乎无位移）则用整齐长度。
                # 入栈统一交给 add_measurement，此处不预先快照。
                self._drawing = True
                self._start = pos
                self._last = pos

    def mouseMoveEvent(self, event):
        if self.image.isNull():
            return
        if self._panning:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, "horizontalScrollBar"):
                    parent.horizontalScrollBar().setValue(
                        parent.horizontalScrollBar().value() - delta.x())
                    parent.verticalScrollBar().setValue(
                        parent.verticalScrollBar().value() - delta.y())
                    break
                parent = parent.parent()
            return
        if self._measure_drag is not None:
            self._drag_annotation(event.pos())
            return
        pos = event.pos()
        img_f = self.map_to_image(pos)
        if self._in_image(QPoint(int(img_f.x()), int(img_f.y()))):
            self.coordChanged.emit(int(img_f.x()), int(img_f.y()))
        if not self._drawing and not self._pending:
            self._update_hover_cursor(pos)
            return
        tool = self.tool
        if tool in FREEHAND_TOOLS and self._drawing:
            self._draw_freehand(self._clamp(img_f))
        elif tool in DRAG_TOOLS and self._drawing:
            self._update_drag_preview(self._clamp(img_f))
        elif tool == ToolID.SCALEBAR and self._drawing:
            self._update_scalebar_preview(self._clamp(img_f))
        elif tool in MULTI_CLICK_TOOLS and self._pending:
            self._update_angle_preview(self._clamp(img_f))

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.unsetCursor()
            return
        if self._measure_drag is not None:
            self._end_annotation_drag()
            return
        if self.image.isNull() or not self._drawing:
            return
        pos = self._event_pos(event)
        tool = self.tool
        self._drawing = False
        if tool in FREEHAND_TOOLS:
            pass  # 已实时绘制
        elif tool in DRAG_TOOLS:
            self._commit_drag(pos)
        elif tool == ToolID.SCALEBAR:
            self._commit_scalebar(pos)
        self._last_mid = QPointF()
        self.update()

    def mouseDoubleClickEvent(self, event):
        """双击文字类标注：编辑文字；其他情况交还默认处理。"""
        if event.button() == Qt.LeftButton and not self.image.isNull():
            img_pt = self.map_to_image(event.pos())
            m = self.select_at(img_pt, slack=self._hit_slack())
            if m is not None and m.kind in ("text", "arrow"):
                self.selected = m
                self._edit_annotation_text(m)
                event.accept()
                return
        event.ignore()

    # ------------------------------------------------------------------
    # 绘制实现
    # ------------------------------------------------------------------
    def _pen_for(self, color, preview=False):
        pen = QPen(color, max(1, self.pen_size))
        if self.dashed and self.tool != ToolID.ERASE:
            pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _effective_color(self):
        if self._button == Qt.RightButton:
            return self.back_color
        return self.pen_color

    def _painter_on(self, target):
        painter = QPainter(target)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.opacity < 1.0:
            painter.setOpacity(self.opacity)
        return painter

    def _draw_freehand(self, pos):
        color = self.back_color if self.tool == ToolID.ERASE else self._effective_color()
        painter = self._painter_on(self.image)
        painter.setPen(self._pen_for(color))
        if self.smooth and self._last_mid is not None:
            # 二次贝塞尔平滑：上一段中点 -> 控制点(上一光标点) -> 新中点
            mid = (QPointF(self._last) + QPointF(pos)) / 2
            path = QPainterPath(self._last_mid)
            path.quadTo(QPointF(self._last), mid)
            painter.drawPath(path)
            self._last_mid = mid
        else:
            painter.drawLine(self._last, pos)
        painter.end()
        self._last = pos
        self.refresh()

    def _draw_dot(self, pos, color):
        """在图像上画一个实心点（单击画笔/橡皮擦的落点）。"""
        r = max(0.5, self.pen_size / 2.0)
        painter = self._painter_on(self.image)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(pos), r, r)
        painter.end()

    def _update_drag_preview(self, pos):
        tool = self.tool
        a, b = self._start, pos
        if tool == ToolID.CALIBRATE:
            self._active_measure = make_calibrate(a, b)
        elif tool == ToolID.DISTANCE:
            self._active_measure = make_distance(a, b)
        elif tool == ToolID.AREA:
            self._active_measure = make_rect_area(a, b)
        elif tool == ToolID.RADIUS:
            self._active_measure = make_circle(a, b)
        elif tool == ToolID.ANNOT_ARROW:
            self._active_measure = make_arrow(a, b)
        else:
            # 形状类：双缓冲预览
            self.preview = self.image.copy()
            painter = self._painter_on(self.preview)
            color = self.back_color if self._button == Qt.RightButton else self.pen_color
            pen = self._pen_for(color)
            painter.setPen(pen)
            if self.fill_shapes:
                fill = QColor(color)
                fill.setAlpha(int(255 * self.opacity))
                painter.setBrush(fill)
            if tool == ToolID.LINE:
                painter.drawLine(a, b)
            elif tool == ToolID.RECT:
                painter.drawRect(QRect(a, b))
            elif tool == ToolID.ELLIPSE:
                painter.drawEllipse(QRect(a, b))
            elif tool == ToolID.ARROW:
                self._paint_arrow(painter, a, b, color)
            painter.end()
        self.update()

    def _update_scalebar_preview(self, pos):
        """比例尺图形拖拽预览（实时显示实际长度）。"""
        self._active_measure = make_scalebar(self._start, pos)
        self.update()

    def _commit_drag(self, pos):
        tool = self.tool
        a, b = self._start, pos
        self._active_measure = None
        self.preview = None
        if distance(QPointF(a), QPointF(b)) < 1.5 and tool not in (ToolID.RECT, ToolID.ELLIPSE):
            self.statusHint.emit("线段太短，已忽略")
            if tool not in MEASURE_TOOLS:
                self._history.pop()  # 形状类按下时压过栈，这里取消
            return

        if tool == ToolID.CALIBRATE:
            px_len = distance(QPointF(a), QPointF(b))
            self._pending_calibrate = (a, b, px_len)
            self.calibrateRequested.emit(a, b, px_len)
            return
        if tool == ToolID.DISTANCE:
            self.add_measurement(make_distance(a, b))
            self.statusHint.emit("距离: %s" % fmt_length(distance(QPointF(a), QPointF(b)), self.scale))
            return
        if tool == ToolID.AREA:
            m = make_rect_area(a, b)
            self.add_measurement(m)
            self.statusHint.emit("面积: %s" % fmt_area(m.px_value, self.scale))
            return
        if tool == ToolID.RADIUS:
            m = make_circle(a, b)
            self.add_measurement(m)
            self.statusHint.emit("圆: %s" % m.value_text(self.scale))
            return
        if tool == ToolID.ANNOT_ARROW:
            self._request_arrow_text(a, b)
            return

        # 形状类提交到图像
        color = self.back_color if self._button == Qt.RightButton else self.pen_color
        painter = self._painter_on(self.image)
        painter.setPen(self._pen_for(color))
        if self.fill_shapes:
            fill = QColor(color)
            fill.setAlpha(int(255 * self.opacity))
            painter.setBrush(fill)
        if tool == ToolID.LINE:
            painter.drawLine(a, b)
        elif tool == ToolID.RECT:
            painter.drawRect(QRect(a, b))
        elif tool == ToolID.ELLIPSE:
            painter.drawEllipse(QRect(a, b))
        elif tool == ToolID.ARROW:
            self._paint_arrow(painter, a, b, color)
        painter.end()
        self.refresh()
        self.imageChanged.emit()

    def _commit_scalebar(self, pos):
        """比例尺图形提交：拖拽用拖出长度；单击用整齐长度。"""
        a, b = self._start, pos
        self._active_measure = None
        if distance(QPointF(a), QPointF(b)) < 3.0:
            # 单击：按整齐像素长度放置
            self._create_scalebar(a)
            return
        if not self.scale.calibrated:
            self.statusHint.emit("请先标定比例尺（测量 → 标定比例尺），当前仅按像素显示")
        m = make_scalebar(a, b)
        self.add_measurement(m)
        self.statusHint.emit("比例尺: %s" % m.value_text(self.scale))

    def _paint_arrow(self, painter, tail, head, color):
        pen = self._pen_for(color)
        painter.setPen(pen)
        painter.drawLine(tail, head)
        dx, dy = head.x() - tail.x(), head.y() - tail.y()
        ang = math.atan2(dy, dx)
        size = max(10.0, self.pen_size * 4)
        for da in (math.radians(150), -math.radians(150)):
            painter.drawLine(head, QPointF(head.x() + size * math.cos(ang + da),
                                           head.y() + size * math.sin(ang + da)))

    def _update_angle_preview(self, pos):
        pts = self._pending + [pos]
        if len(pts) == 2:
            self._active_measure = Measurement(kind="distance", points=[QPointF(pts[0]), QPointF(pts[1])],
                                               px_value=distance(QPointF(pts[0]), QPointF(pts[1])))
        elif len(pts) >= 3:
            self._active_measure = make_angle(pts[0], pts[-2], pts[-1])
        self.update()

    def _apply_bucket(self, pos):
        color = self.back_color if self._button == Qt.RightButton else self.pen_color
        try:
            self.image = IU.flood_fill(self.image, pos, color, opacity=self.opacity)
        except Exception as exc:  # noqa: BLE001
            logger.exception("油漆桶失败")
            self.statusHint.emit("油漆桶失败: %s" % exc)
            self._history.pop()
            return
        self.refresh()
        self.imageChanged.emit()
        self.statusHint.emit("已填充区域")

    # ------------------------------------------------------------------
    # 文字 / 比例尺图形 / 箭头标注
    # ------------------------------------------------------------------
    def _request_text(self, pos):
        from .dialogs import TextInputDialog
        dlg = TextInputDialog(self)
        if dlg.exec_():
            text, size = dlg.values()
            if not text.strip():
                return
            color = self.pen_color
            m = make_text(pos, text)
            m.color = color
            if self.tool == ToolID.ANNOT_TEXT:
                self.add_measurement(m)
                self.statusHint.emit("已添加文字标注")
            else:
                self._draw_text_on_image(pos, text, size, color)
        else:
            self.statusHint.emit("已取消文字输入")

    def _draw_text_on_image(self, pos, text, size, color):
        from PyQt5.QtGui import QFont, QFontMetrics
        self.begin_action("image")
        painter = self._painter_on(self.image)
        font = QFont(self.font())
        font.setPixelSize(max(8, size))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        lines = text.split("\n")
        w = max(metrics.horizontalAdvance(line) for line in lines)
        h = metrics.height() * len(lines)
        box = QRectF(pos.x() - 4, pos.y() - h - 6, w + 10, h + 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawRect(box)
        y = box.top() + metrics.ascent() + 3
        for line in lines:
            painter.setPen(color)
            painter.drawText(int(box.left() + 5), int(y), line)
            y += metrics.height()
        painter.end()
        self.refresh()
        self.imageChanged.emit()
        self.statusHint.emit("已添加文字")

    def _request_arrow_text(self, tail, head):
        from .dialogs import TextInputDialog
        dlg = TextInputDialog(self, title="箭头标注", placeholder="输入标注文字（可留空）")
        if dlg.exec_():
            text, _ = dlg.values()
            m = make_arrow(tail, head, text.strip())
            self.add_measurement(m)
            self.statusHint.emit("已添加箭头标注")
        else:
            m = make_arrow(tail, head, "")
            self.add_measurement(m)

    def _create_scalebar(self, pos):
        if not self.scale.calibrated:
            self.statusHint.emit("请先标定比例尺（测量 → 标定比例尺）")
            self.calibrateRequested.emit(QPoint(), QPoint(), 0.0)
            return
        px = nice_scalebar_pixels(self.scale.pixels_per_unit)
        a = QPoint(pos.x(), pos.y())
        b = QPoint(pos.x() + int(round(px)), pos.y())
        self.add_measurement(make_scalebar(a, b))
        self.statusHint.emit("已绘制比例尺图形")
