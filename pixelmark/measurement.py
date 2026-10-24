# -*- coding: utf-8 -*-
"""测量数据模型与几何计算。

比例尺（Scale）把"像素长度"换算为"实际长度"：``实际值 = 像素值 / pixels_per_unit``。
所有几何函数均为纯函数，便于单元测试（不依赖 GUI 的测试见 tests/）。
"""

import math
from dataclasses import dataclass, field, replace

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from .util.errors import ScaleError
from .util.logging import get_logger

logger = get_logger("measurement")

# 测量标注默认颜色（醒目红）与预览色
MEASURE_COLOR = QColor(211, 47, 47)
PREVIEW_COLOR = QColor(211, 47, 47, 160)
HALO_COLOR = QColor(255, 255, 255)
SELECT_COLOR = QColor(11, 87, 208)

KIND_NAMES = {
    "distance": "距离",
    "angle": "角度",
    "rect_area": "矩形面积",
    "circle": "圆",
    "text": "文字标注",
    "arrow": "箭头标注",
    "scalebar": "比例尺",
    "calibrate": "标定线",
}


# ---------------------------------------------------------------------------
# 比例尺
# ---------------------------------------------------------------------------

# 长度单位 -> 毫米 的换算系数（px 为像素，不可与长度单位换算）
UNIT_TO_MM = {
    "μm": 0.001,
    "um": 0.001,
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "mil": 0.0254,
}

# 常见单位预设（标定对话框与显示单位切换用）
UNIT_PRESETS = ["mm", "cm", "m", "μm", "in", "mil"]


def unit_to_mm_factor(unit):
    """单位 -> 毫米系数；像素或未知单位返回 None。"""
    return UNIT_TO_MM.get(str(unit).strip())


def convert_length(value, from_unit, to_unit):
    """长度值单位换算；任一单位为像素或未知时返回原值。"""
    f1 = unit_to_mm_factor(from_unit)
    f2 = unit_to_mm_factor(to_unit)
    if f1 is None or f2 is None:
        return value
    return value * f1 / f2


@dataclass
class Scale:
    """像素 -> 实际单位 的比例尺。

    pixels_per_unit 为 None 表示未标定（仅输出像素值）。
    """

    pixels_per_unit: float = None
    unit: str = "mm"

    @property
    def calibrated(self):
        return self.pixels_per_unit is not None and self.pixels_per_unit > 0

    def to_unit(self, px_value):
        """像素值 -> 实际值；未标定时原样返回。"""
        if not self.calibrated:
            return None
        return px_value / self.pixels_per_unit

    def convert_to(self, unit):
        """切换到另一个长度单位（换算 pixels_per_unit，标定关系不变）。

        像素单位或未知单位不可换算，返回自身。
        """
        unit = str(unit).strip()
        if not self.calibrated or unit == self.unit:
            return self
        f_from = unit_to_mm_factor(self.unit)
        f_to = unit_to_mm_factor(unit)
        if f_from is None or f_to is None:
            return self
        return Scale(pixels_per_unit=self.pixels_per_unit * f_to / f_from,
                     unit=unit)

    def describe(self):
        if not self.calibrated:
            return "未标定（测量结果为像素值）"
        return "1 px = %.4g %s（1 %s = %.2f px）" % (
            1.0 / self.pixels_per_unit, self.unit, self.unit, self.pixels_per_unit)

    def describe_compact(self):
        """紧凑形式（左侧面板标签用，避免换行撑高布局）。"""
        if not self.calibrated:
            return "未标定（像素值）"
        return "%.4g px/%s" % (self.pixels_per_unit, self.unit)

    @classmethod
    def from_lengths(cls, pixel_length, real_length, unit):
        """由线段像素长度与实际长度构造，参数非法时抛出 ScaleError。"""
        if pixel_length <= 0:
            raise ScaleError("标定线段的像素长度必须大于 0")
        if real_length <= 0:
            raise ScaleError("实际长度必须大于 0")
        return cls(pixels_per_unit=pixel_length / float(real_length), unit=str(unit))


# ---------------------------------------------------------------------------
# 几何计算（纯函数）
# ---------------------------------------------------------------------------

def distance(p1, p2):
    """两点间欧氏距离（像素）。"""
    return math.hypot(p2.x() - p1.x(), p2.y() - p1.y())


def angle_at(vertex, p1, p2):
    """p1-vertex-p2 在 vertex 处的夹角（度，0..180）。"""
    v1 = (p1.x() - vertex.x(), p1.y() - vertex.y())
    v2 = (p2.x() - vertex.x(), p2.y() - vertex.y())
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cosv))


def rect_area(rect):
    """QRectF 面积（像素²）。"""
    return abs(rect.width() * rect.height())


def circle_metrics(center, radius):
    """由圆心与半径返回 (半径, 直径, 周长, 面积)（像素）。"""
    r = abs(radius)
    return r, 2 * r, 2 * math.pi * r, math.pi * r * r


def polygon_area(points):
    """鞋带公式求多边形面积（像素²）。"""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i].x(), points[i].y()
        x2, y2 = points[(i + 1) % len(points)].x(), points[(i + 1) % len(points)].y()
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------

def _smart(value, digits=2):
    """智能有效位数：大数少小数位，小数保留精度。"""
    if value is None:
        return "-"
    a = abs(value)
    if a == 0:
        return "0"
    if a >= 1000:
        return "%.0f" % value
    if a >= 100:
        return "%.1f" % value
    if a >= 10:
        return "%.2f" % value
    return ("%." + str(digits) + "f") % value


def fmt_length(px_value, scale=None, digits=2):
    """长度格式化：未标定 -> '123.4 px'；已标定 -> '123.4 px (12.34 mm)'。"""
    text = "%s px" % _smart(px_value, digits)
    if scale is not None and scale.calibrated:
        real = scale.to_unit(px_value)
        if real is not None:
            text += "（%s %s）" % (_smart(real, digits), scale.unit)
    return text


def fmt_area(px_value, scale=None, digits=2):
    """面积格式化。"""
    text = "%s px²" % _smart(px_value, 0)
    if scale is not None and scale.calibrated:
        real = scale.to_unit(px_value)  # 线性比例 -> 面积需平方
        if real is not None:
            text += "（%s %s²）" % (_smart(real, 0), scale.unit)
    return text


def fmt_angle(deg):
    return "%.1f°" % deg


def nice_scalebar_pixels(pixels_per_unit):
    """为比例尺图形挑选一个"整齐"的像素长度（1/2/5 x 10^n，80..240px）。"""
    if not pixels_per_unit or pixels_per_unit <= 0:
        return 120.0
    target = 160.0  # 期望像素长度
    raw = target * pixels_per_unit
    exp = math.floor(math.log10(raw)) if raw > 0 else 0
    best = None
    for e in (exp - 1, exp, exp + 1):
        for m in (1.0, 2.0, 5.0):
            val = m * (10 ** e)
            px = val / pixels_per_unit
            if 80 <= px <= 240:
                if best is None or abs(px - target) < abs(best[1] - target):
                    best = (val, px)
    if best is None:
        return 120.0
    return best[1]


def nice_scalebar_value(pixels_per_unit):
    """比例尺图形对应的实际长度值（与 nice_scalebar_pixels 对应）。"""
    if not pixels_per_unit or pixels_per_unit <= 0:
        return None
    return nice_scalebar_pixels(pixels_per_unit) * pixels_per_unit


# ---------------------------------------------------------------------------
# 测量对象
# ---------------------------------------------------------------------------

@dataclass
class Measurement:
    """一个测量/标注对象（叠加层，可删除，不破坏原图）。"""

    kind: str                       # distance/angle/rect_area/circle/text/arrow/scalebar
    points: list = field(default_factory=list)   # QPointF 列表
    label: str = ""                 # 附加文字（标注内容）
    color: QColor = field(default_factory=lambda: QColor(MEASURE_COLOR))
    # 预计算的显示值（像素）
    px_value: float = 0.0
    px_value2: float = 0.0          # 辅助值（如面积）

    # ---- 数值描述 ----
    def value_text(self, scale=None):
        """主数值的人类可读描述。"""
        if self.kind == "distance":
            return fmt_length(self.px_value, scale)
        if self.kind == "angle":
            return fmt_angle(self.px_value)
        if self.kind == "rect_area":
            return "W×H %s × %s｜面积 %s" % (
                fmt_length(abs(self.points[1].x() - self.points[0].x()), scale),
                fmt_length(abs(self.points[1].y() - self.points[0].y()), scale),
                fmt_area(self.px_value, scale))
        if self.kind == "circle":
            r, d, c, a = circle_metrics(self.points[0], self.px_value)
            return "R %s｜D %s｜面积 %s" % (
                fmt_length(r, scale), fmt_length(d, scale), fmt_area(a, scale))
        if self.kind in ("text", "arrow"):
            return self.label or KIND_NAMES.get(self.kind, "")
        if self.kind == "scalebar":
            if scale and scale.calibrated:
                # 使用该比例尺图形的真实像素长度（拖拽定义的任意长度均可）
                real = self.px_value / scale.pixels_per_unit
                return "比例尺 %s %s" % (_smart(real), scale.unit)
            return "比例尺 %s px" % _smart(self.px_value)
        return ""

    def title(self, scale=None):
        """列表/导出的标题。"""
        name = KIND_NAMES.get(self.kind, self.kind)
        text = self.value_text(scale)
        return "%s：%s" % (name, text) if text else name

    def csv_row(self, index, scale=None):
        pts = "; ".join("(%d,%d)" % (p.x(), p.y()) for p in self.points)
        px = "%g" % self.px_value if self.px_value else ""
        real = ""
        if scale and scale.calibrated and self.px_value:
            if self.kind in ("distance", "circle"):
                real = "%g %s" % (self.px_value / scale.pixels_per_unit, scale.unit)
            elif self.kind in ("rect_area",):
                real = "%g %s2" % (self.px_value / (scale.pixels_per_unit ** 2), scale.unit)
        return [str(index), KIND_NAMES.get(self.kind, self.kind), pts, px, real,
                self.label.replace(",", "，")]

    # ---- 命中测试 ----
    def hit_test(self, point, slack=6.0):
        for p in self.points:
            if distance(p, point) <= slack:
                return True
        if self.kind in ("distance", "arrow", "calibrate") and len(self.points) >= 2:
            if _dist_to_segment(point, self.points[0], self.points[1]) <= slack:
                return True
        if self.kind == "rect_area" and len(self.points) >= 2:
            rect = QRectF(self.points[0], self.points[1]).normalized()
            rect.adjust(-slack, -slack, slack, slack)
            if rect.contains(point):
                return True
        if self.kind == "circle" and len(self.points) >= 2:
            r = distance(self.points[0], self.points[1])
            if abs(distance(self.points[0], point) - r) <= slack:
                return True
        if self.kind in ("text", "arrow"):
            box = self.text_box()
            if not box.isNull():
                box.adjust(-slack, -slack, slack, slack)
                if box.contains(point):
                    return True
        return False

    def text_box(self, font=None):
        """文字/箭头标注的文本框（与绘制一致），无文字时返回空矩形。"""
        text = self.label or ""
        if not text:
            return QRectF()
        f = QFont(font) if font is not None else QFont()
        f.setPixelSize(16)
        metrics = QFontMetrics(f)
        lines = text.split("\n")
        w = max(metrics.horizontalAdvance(line) for line in lines)
        h = metrics.height() * len(lines)
        if self.kind == "arrow" and len(self.points) >= 2:
            head = self.points[1]
            return QRectF(head.x() + 6, head.y() - h - 6, w + 10, h + 8)
        if not self.points:
            return QRectF()
        pos = self.points[0]
        return QRectF(pos.x() - 4, pos.y() - h - 6, w + 10, h + 8)

    # ---- 变换（拖动调整位置 / 拖动控制点改形状） ----
    def copy(self):
        """独立副本（点列表复制；撤销快照与原对象互不影响）。"""
        return replace(self, points=[QPointF(p) for p in self.points])

    def recompute(self):
        """按当前点重算预计算数值（拖拽调整后必须调用）。"""
        n = len(self.points)
        if n >= 2 and self.kind in ("distance", "arrow", "scalebar", "calibrate"):
            self.px_value = distance(self.points[0], self.points[1])
        elif n >= 3 and self.kind == "angle":
            self.px_value = angle_at(self.points[1], self.points[0], self.points[2])
        elif n >= 2 and self.kind == "rect_area":
            rect = QRectF(self.points[0], self.points[1]).normalized()
            self.points = [rect.topLeft(), rect.bottomRight()]
            self.px_value = rect_area(rect)
        elif n >= 2 and self.kind == "circle":
            self.px_value = distance(self.points[0], self.points[1])
        return self

    def translated(self, dx, dy):
        """整体平移后的新对象。"""
        pts = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]
        return replace(self, points=pts).recompute()

    def with_point(self, index, point):
        """移动单个控制点后的新对象（index 越界时返回平移 0 的副本）。"""
        pts = [QPointF(p) for p in self.points]
        if 0 <= index < len(pts):
            pts[index] = QPointF(point)
        return replace(self, points=pts).recompute()

    def bounds(self):
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    # ---- 绘制 ----
    def draw(self, painter, scale=None, selected=False, font=None):
        color = SELECT_COLOR if selected else self.color
        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            if self.kind == "distance":
                self._draw_distance(painter, pen, scale)
            elif self.kind == "angle":
                self._draw_angle(painter, pen, scale)
            elif self.kind == "rect_area":
                self._draw_rect(painter, pen, scale)
            elif self.kind == "circle":
                self._draw_circle(painter, pen, scale)
            elif self.kind in ("text", "arrow"):
                self._draw_text_like(painter, pen, scale, font)
            elif self.kind == "scalebar":
                self._draw_scalebar(painter, pen, scale)
            elif self.kind == "calibrate":
                self._draw_calibrate(painter, pen, scale)
        except Exception as exc:  # noqa: BLE001 - 单个测量绘制失败不影响整体
            logger.warning("绘制测量对象失败(%s): %s", self.kind, exc)

    # -- 各类型绘制 --
    def _draw_distance(self, painter, pen, scale):
        a, b = self.points[0], self.points[1]
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(a, b)
        # 端点垂直刻度
        self._draw_end_ticks(painter, a, b, pen.color())
        self._draw_label(painter, (a + b) / 2, self.value_text(scale))

    def _draw_angle(self, painter, pen, scale):
        p1, v, p2 = self.points
        painter.setPen(pen)
        painter.drawLine(v, p1)
        painter.drawLine(v, p2)
        r = 34.0
        a1 = math.atan2(p1.y() - v.y(), p1.x() - v.x())
        a2 = math.atan2(p2.y() - v.y(), p2.x() - v.x())
        rect = QRectF(v.x() - r, v.y() - r, 2 * r, 2 * r)
        # Qt 角度为 1/16 度，逆时针为正；y 轴向下需取反
        start = int(-a1 * 180 / math.pi * 16)
        span = int((a1 - a2) * 180 / math.pi * 16)
        if span < 0:
            span += 360 * 16
        if span > 180 * 16:
            span -= 360 * 16
        painter.drawArc(rect, start, span)
        for p in (p1, v, p2):
            self._draw_dot(painter, p, pen.color())
        self._draw_label(painter, v + QPointF(0, -14), self.value_text(scale))

    def _draw_rect(self, painter, pen, scale):
        rect = QRectF(self.points[0], self.points[1]).normalized()
        pen.setWidth(2)
        painter.setPen(pen)
        fill = QColor(self.color.red(), self.color.green(), self.color.blue(), 40)
        painter.setBrush(fill)
        painter.drawRect(rect)
        self._draw_label(painter, rect.topLeft() + QPointF(0, -6), self.value_text(scale))

    def _draw_circle(self, painter, pen, scale):
        c = self.points[0]
        r = distance(c, self.points[1])
        painter.setPen(pen)
        painter.drawEllipse(c, r, r)
        pen2 = QPen(pen)
        pen2.setStyle(Qt.DashLine)
        painter.setPen(pen2)
        painter.drawLine(c, self.points[1])
        self._draw_dot(painter, c, pen.color())
        self._draw_label(painter, (c + self.points[1]) / 2 + QPointF(8, -4),
                         self.value_text(scale))

    def _draw_text_like(self, painter, pen, scale, font):
        f = QFont(font) if font is not None else QFont()
        f.setPixelSize(16)
        painter.setFont(f)
        text = self.label or ""
        if not text:
            return
        if self.kind == "arrow" and len(self.points) >= 2:
            tail, head = self.points[0], self.points[1]
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(tail, head)
            self._draw_arrow_head(painter, tail, head, pen.color(), size=14)
        box = self.text_box(font)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRect(box)
        self._draw_plain_text(painter, box.topLeft() + QPointF(4, QFontMetrics(f).ascent() + 2),
                              text, self.color)

    def _draw_scalebar(self, painter, pen, scale):
        # 点: [起点, 终点]
        a, b = self.points[0], self.points[1]
        px_len = distance(a, b)
        if px_len < 1:
            return
        horizontal = abs(b.x() - a.x()) >= abs(b.y() - a.y())
        segs = 4
        seg_w = px_len / segs
        painter.setPen(Qt.NoPen)
        for i in range(segs):
            if horizontal:
                x0 = a.x() + i * seg_w
                r = QRectF(x0, a.y() - 7, seg_w, 14)
            else:
                y0 = a.y() + i * seg_w
                r = QRectF(a.x() - 7, y0, 14, seg_w)
            painter.setBrush(self.color if i % 2 == 0 else QColor(255, 255, 255))
            painter.drawRect(r)
        # 边框与刻度
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.color, 1.5))
        if horizontal:
            painter.drawRect(QRectF(a.x(), a.y() - 7, px_len, 14))
            for i in range(segs + 1):
                x = a.x() + i * seg_w
                ln = 9 if i % 2 == 0 else 5
                painter.drawLine(x, a.y() + 7, x, a.y() + 7 + ln)
        else:
            painter.drawRect(QRectF(a.x() - 7, a.y(), 14, px_len))
            for i in range(segs + 1):
                y = a.y() + i * seg_w
                ln = 9 if i % 2 == 0 else 5
                painter.drawLine(a.x() + 7, y, a.x() + 7 + ln, y)
        if scale and scale.calibrated:
            real = self.px_value / scale.pixels_per_unit
            text = "%s %s" % (_smart(real), scale.unit)
        else:
            text = "%d px" % round(px_len)
        f = QFont()
        f.setPixelSize(14)
        painter.setFont(f)
        metrics = QFontMetrics(f)
        tw = metrics.horizontalAdvance(text)
        if horizontal:
            pos = QPointF(a.x() + px_len / 2 - tw / 2, a.y() + 7 + 22)
        else:
            pos = QPointF(a.x() + 7 + 22, a.y() + px_len / 2 - 6)
        self._draw_plain_text(painter, pos, text, self.color)

    def _draw_calibrate(self, painter, pen, scale):
        a, b = self.points[0], self.points[1]
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(a, b)
        self._draw_end_ticks(painter, a, b, self.color)
        if scale and scale.calibrated:
            text = "标定：1 %s = %.2f px" % (scale.unit, scale.pixels_per_unit)
        else:
            text = "标定线"
        self._draw_label(painter, (a + b) / 2, text)

    # -- 绘制辅助 --
    def _draw_dot(self, painter, p, color, r=3.5):
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(p, r, r)

    def _draw_end_ticks(self, painter, a, b, color, size=7.0):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln * size, dx / ln * size
        pen = QPen(color, 2)
        painter.setPen(pen)
        for p in (a, b):
            painter.drawLine(QPointF(p.x() - nx, p.y() - ny), QPointF(p.x() + nx, p.y() + ny))

    def _draw_arrow_head(self, painter, tail, head, color, size=14.0):
        dx, dy = head.x() - tail.x(), head.y() - tail.y()
        ang = math.atan2(dy, dx)
        painter.setPen(QPen(color, 2))
        for da in (math.radians(150), -math.radians(150)):
            painter.drawLine(head, QPointF(
                head.x() + size * math.cos(ang + da),
                head.y() + size * math.sin(ang + da)))

    def _draw_label(self, painter, center, text):
        if not text:
            return
        f = QFont()
        f.setPixelSize(14)
        painter.setFont(f)
        metrics = QFontMetrics(f)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        box = QRectF(center.x() - tw / 2 - 5, center.y() - th / 2 - 3, tw + 10, th + 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.drawRect(box)
        self._draw_plain_text(painter, box.topLeft() + QPointF(5, metrics.ascent() + 3),
                              text, self.color)

    def _draw_plain_text(self, painter, pos, text, color):
        """带白色描边的文字，保证在任意背景上可读。"""
        f = QFont(painter.font())
        path = QPainterPath()
        y = pos.y()
        for line in text.split("\n"):
            path.addText(pos.x(), y, f, line)
            y += QFontMetrics(f).height()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(HALO_COLOR, 3.0)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)


def _dist_to_segment(p, a, b):
    """点 p 到线段 ab 的距离。"""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    ln2 = dx * dx + dy * dy
    if ln2 < 1e-9:
        return distance(p, a)
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / ln2))
    return distance(p, QPointF(a.x() + t * dx, a.y() + t * dy))


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_distance(p1, p2):
    return Measurement(kind="distance", points=[QPointF(p1), QPointF(p2)],
                       px_value=distance(QPointF(p1), QPointF(p2)))


def make_angle(p1, vertex, p2):
    return Measurement(kind="angle", points=[QPointF(p1), QPointF(vertex), QPointF(p2)],
                       px_value=angle_at(QPointF(vertex), QPointF(p1), QPointF(p2)))


def make_rect_area(p1, p2):
    rect = QRectF(QPointF(p1), QPointF(p2)).normalized()
    return Measurement(kind="rect_area", points=[rect.topLeft(), rect.bottomRight()],
                       px_value=rect_area(rect))


def make_circle(center, edge):
    return Measurement(kind="circle", points=[QPointF(center), QPointF(edge)],
                       px_value=distance(QPointF(center), QPointF(edge)))


def make_text(pos, label):
    return Measurement(kind="text", points=[QPointF(pos)], label=label)


def make_arrow(tail, head, label=""):
    return Measurement(kind="arrow", points=[QPointF(tail), QPointF(head)], label=label)


def make_scalebar(a, b):
    return Measurement(kind="scalebar", points=[QPointF(a), QPointF(b)],
                       px_value=distance(QPointF(a), QPointF(b)))


def make_calibrate(a, b):
    return Measurement(kind="calibrate", points=[QPointF(a), QPointF(b)],
                       px_value=distance(QPointF(a), QPointF(b)))
