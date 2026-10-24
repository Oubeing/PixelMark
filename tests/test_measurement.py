# -*- coding: utf-8 -*-
"""测量几何与比例尺的单元测试（纯函数，无需 GUI 环境）。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor

from pixelmark.measurement import (Scale, angle_at, circle_metrics, distance,
                                   fmt_angle, fmt_area, fmt_length,
                                   make_angle, make_arrow, make_calibrate,
                                   make_circle, make_distance, make_rect_area,
                                   make_scalebar, make_text, nice_scalebar_pixels,
                                   polygon_area)

_app = None


def _qapp():
    global _app
    if _app is None:
        from PyQt5.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])
    return _app


class TestGeometry(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance(QPointF(0, 0), QPointF(3, 4)), 5.0)
        self.assertAlmostEqual(distance(QPointF(-1, -1), QPointF(2, 3)), 5.0)

    def test_angle_right(self):
        self.assertAlmostEqual(angle_at(QPointF(0, 0), QPointF(1, 0), QPointF(0, 1)), 90.0)

    def test_angle_straight(self):
        self.assertAlmostEqual(angle_at(QPointF(0, 0), QPointF(1, 0), QPointF(-1, 0)), 180.0)

    def test_angle_zero(self):
        self.assertAlmostEqual(angle_at(QPointF(0, 0), QPointF(1, 0), QPointF(2, 0)), 0.0)

    def test_angle_degenerate(self):
        self.assertAlmostEqual(angle_at(QPointF(0, 0), QPointF(0, 0), QPointF(1, 0)), 0.0)

    def test_rect_area(self):
        self.assertAlmostEqual(
            polygon_area([QPointF(0, 0), QPointF(10, 0), QPointF(10, 5), QPointF(0, 5)]), 50.0)

    def test_circle_metrics(self):
        r, d, c, a = circle_metrics(QPointF(0, 0), 2.0)
        self.assertAlmostEqual(r, 2.0)
        self.assertAlmostEqual(d, 4.0)
        self.assertAlmostEqual(c, 4 * math.pi)
        self.assertAlmostEqual(a, 4 * math.pi)


class TestScale(unittest.TestCase):
    def test_uncalibrated(self):
        s = Scale()
        self.assertFalse(s.calibrated)
        self.assertIsNone(s.to_unit(100))
        self.assertIn("未标定", s.describe())

    def test_from_lengths(self):
        s = Scale.from_lengths(300.0, 10.0, "mm")
        self.assertTrue(s.calibrated)
        self.assertAlmostEqual(s.pixels_per_unit, 30.0)
        self.assertAlmostEqual(s.to_unit(60.0), 2.0)

    def test_invalid(self):
        from pixelmark.util.errors import ScaleError
        with self.assertRaises(ScaleError):
            Scale.from_lengths(0.0, 10.0, "mm")
        with self.assertRaises(ScaleError):
            Scale.from_lengths(100.0, 0.0, "mm")
        with self.assertRaises(ScaleError):
            Scale.from_lengths(100.0, -1.0, "mm")

    def test_format(self):
        s = Scale.from_lengths(300.0, 10.0, "mm")  # 30px = 1mm
        self.assertEqual(fmt_length(60.0, None), "60.00 px")
        self.assertIn("mm", fmt_length(60.0, s))
        self.assertIn("px²", fmt_area(900.0, None))
        self.assertIn("mm²", fmt_area(900.0, s))
        self.assertEqual(fmt_angle(45.0), "45.0°")

    def test_nice_scalebar(self):
        px = nice_scalebar_pixels(30.0)   # 30px/mm
        self.assertTrue(60 <= px <= 300)
        px2 = nice_scalebar_pixels(None)
        self.assertGreater(px2, 0)


class TestMeasurementObjects(unittest.TestCase):
    def test_make_distance(self):
        m = make_distance(QPointF(0, 0), QPointF(30, 40))
        self.assertEqual(m.kind, "distance")
        self.assertAlmostEqual(m.px_value, 50.0)
        self.assertIn("50", m.value_text())

    def test_make_angle(self):
        # make_angle(p1, vertex, p2)：顶点在原点时为 90°
        m = make_angle(QPointF(10, 0), QPointF(0, 0), QPointF(0, 10))
        self.assertEqual(m.kind, "angle")
        self.assertAlmostEqual(m.px_value, 90.0)
        # 45° 情形
        m2 = make_angle(QPointF(0, 0), QPointF(10, 0), QPointF(0, 10))
        self.assertAlmostEqual(m2.px_value, 45.0)

    def test_make_rect_area(self):
        m = make_rect_area(QPointF(10, 10), QPointF(60, 40))   # 50 x 30
        self.assertAlmostEqual(m.px_value, 1500.0)
        text = m.value_text()
        self.assertIn("面积", text)

    def test_make_circle(self):
        m = make_circle(QPointF(0, 0), QPointF(25, 0))
        self.assertAlmostEqual(m.px_value, 25.0)
        self.assertIn("R", m.value_text())

    def test_make_text_arrow_scalebar_calibrate(self):
        self.assertEqual(make_text(QPointF(1, 2), "hi").kind, "text")
        self.assertEqual(make_arrow(QPointF(0, 0), QPointF(5, 5), "x").label, "x")
        self.assertEqual(make_scalebar(QPointF(0, 0), QPointF(100, 0)).kind, "scalebar")
        self.assertEqual(make_calibrate(QPointF(0, 0), QPointF(10, 0)).kind, "calibrate")

    def test_hit_test(self):
        m = make_distance(QPointF(0, 0), QPointF(100, 0))
        self.assertTrue(m.hit_test(QPointF(50, 2)))
        self.assertFalse(m.hit_test(QPointF(50, 40)))

    def test_csv_row(self):
        s = Scale.from_lengths(30.0, 1.0, "mm")
        m = make_distance(QPointF(0, 0), QPointF(60, 0))
        row = m.csv_row(1, s)
        self.assertEqual(row[0], "1")
        self.assertIn("2", row[4])   # 60px / 30 = 2 mm

    def test_draw_does_not_raise(self):
        """所有类型的绘制均可安全执行（离屏 QImage + QPainter）。"""
        _qapp()  # 离屏 QPainter 需要 QApplication 实例
        from PyQt5.QtGui import QImage, QPainter
        image = QImage(400, 300, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        scale = Scale.from_lengths(30.0, 1.0, "mm")
        items = [
            make_distance(QPointF(10, 10), QPointF(110, 60)),
            make_angle(QPointF(10, 10), QPointF(60, 60), QPointF(110, 10)),
            make_rect_area(QPointF(150, 10), QPointF(250, 110)),
            make_circle(QPointF(300, 60), QPointF(350, 60)),
            make_text(QPointF(10, 200), "标注文字"),
            make_arrow(QPointF(150, 200), QPointF(250, 180), "裂纹"),
            make_scalebar(QPointF(10, 280), QPointF(160, 280)),
            make_calibrate(QPointF(200, 280), QPointF(320, 280)),
        ]
        for m in items:
            m.draw(painter, scale, selected=False)          # 不应抛异常
            m.draw(painter, scale, selected=True)
            self.assertIn(m.kind, m.title(scale) + m.kind)  # title 可用
        painter.end()
        self.assertFalse(image.isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
