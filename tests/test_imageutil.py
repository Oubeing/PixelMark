# -*- coding: utf-8 -*-
"""图像处理模块单元测试（修复验证 + 兼容性 + 边界保护）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication

from pixelmark.util import imageutil as IU
from pixelmark.util.errors import ImageLoadError

_app = None


def _qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def make_image(w, h, color_fn):
    img = QImage(w, h, QImage.Format_RGB32)
    for y in range(h):
        for x in range(w):
            img.setPixel(x, y, QColor(*color_fn(x, y)).rgb())
    return img


class TestConversions(unittest.TestCase):
    def setUp(self):
        _qapp()

    def test_roundtrip(self):
        img = make_image(13, 7, lambda x, y: (x * 15 % 256, y * 30 % 256, 128))
        arr = IU.qimage_to_np(img)
        self.assertEqual(arr.shape, (7, 13, 4))
        back = IU.np_to_qimage(arr)
        for y in range(7):
            for x in range(13):
                self.assertEqual(img.pixel(x, y), back.pixel(x, y))

    def test_grayscale_format(self):
        img = make_image(8, 8, lambda x, y: (100, 100, 100))
        g = IU.gray(img)
        self.assertIn(g.format(), (QImage.Format_Grayscale8, QImage.Format_Indexed8,
                                   QImage.Format_RGB32, QImage.Format_ARGB32))
        # 灰度值应接近 100
        px = QColor.fromRgba(g.pixel(4, 4))
        self.assertAlmostEqual(px.red(), 100, delta=2)

    def test_null_image_raises(self):
        with self.assertRaises(ImageLoadError):
            IU.qimage_to_np(QImage())


class TestAdjustments(unittest.TestCase):
    """验证坐标寻址正确 + 数值行为。"""

    def setUp(self):
        _qapp()

    def test_brightness_no_transpose_artifact(self):
        """非正方形图像：调节后 x>=height 区域也必须是正确结果（此前此处花屏）。"""
        img = make_image(20, 6, lambda x, y: (100, 100, 100))
        out = IU.adjustBright(img, 10)
        for y in range(6):
            for x in range(20):
                c = QColor.fromRgba(out.pixel(x, y))
                self.assertEqual((c.red(), c.green(), c.blue()), (110, 110, 110),
                                 "像素(%d,%d) 结果错误" % (x, y))

    def test_brightness_exact(self):
        img = make_image(10, 10, lambda x, y: (x * 25, 255 - y * 25, 128))
        out = IU.adjustBright(img, 30)
        for y in range(10):
            for x in range(10):
                a = QColor.fromRgba(img.pixel(x, y))
                b = QColor.fromRgba(out.pixel(x, y))
                for ch in range(3):
                    expect = min(255, a.getRgb()[ch] + 30)
                    self.assertLessEqual(abs(b.getRgb()[ch] - expect), 0)

    def test_brightness_clip(self):
        img = make_image(4, 4, lambda x, y: (250, 5, 128))
        out = IU.adjustBright(img, 10)
        c = QColor.fromRgba(out.pixel(0, 0))
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 15, 138))

    def test_warm_positive_and_negative(self):
        img = make_image(4, 4, lambda x, y: (100, 100, 100))
        warm = QColor.fromRgba(IU.adjustWarm(img, 50).pixel(0, 0))
        self.assertEqual((warm.red(), warm.green(), warm.blue()), (150, 150, 100))
        cool = QColor.fromRgba(IU.adjustWarm(img, -50).pixel(0, 0))
        self.assertEqual((cool.red(), cool.green(), cool.blue()), (100, 100, 150))

    def test_contrast(self):
        img = make_image(4, 4, lambda x, y: (200, 50, 128))
        out = IU.adjustContrast(img, 50)
        c = QColor.fromRgba(out.pixel(0, 0))
        self.assertGreater(c.red(), 200)   # 亮处更亮
        self.assertLess(c.green(), 50)     # 暗处更暗

    def test_saturation_gray_stays_gray(self):
        img = make_image(4, 4, lambda x, y: (128, 128, 128))
        out = IU.adjustSaturation(img, 100)
        c = QColor.fromRgba(out.pixel(0, 0))
        self.assertEqual((c.red(), c.green(), c.blue()), (128, 128, 128))

    def test_saturation_color_changes(self):
        img = make_image(4, 4, lambda x, y: (200, 100, 100))
        # S_hsv(该色)=128，减 128 后为 0 -> 灰度
        out = IU.adjustSaturation(img, -128)
        c = QColor.fromRgba(out.pixel(0, 0))
        self.assertEqual(c.red(), c.green())
        self.assertEqual(c.green(), c.blue())

    def test_saturation_full_saturation(self):
        img = make_image(4, 4, lambda x, y: (255, 0, 0))
        out = IU.adjustSaturation(img, 100)
        c = QColor.fromRgba(out.pixel(0, 0))
        # 与 Qt 颜色链路一致的结果（HSL 标准公式在 L>=0.5 的 ±1 舍入）
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 1, 1))


class TestFilters(unittest.TestCase):
    def setUp(self):
        _qapp()
        self.img = make_image(48, 32, lambda x, y: (x * 5 % 256, y * 8 % 256, 128))

    def _assert_valid(self, out, name):
        self.assertIsNotNone(out, name)
        self.assertFalse(out.isNull(), name)
        self.assertEqual((out.width(), out.height()), (48, 32), name)

    def test_gray(self):
        self._assert_valid(IU.gray(self.img), "gray")

    def test_binary(self):
        out = IU.binaryzation(self.img)
        self._assert_valid(out, "binary")
        colors = {QColor.fromRgba(out.pixel(x, y)).red()
                  for y in range(32) for x in range(48)}
        self.assertTrue(colors.issubset({0, 255}), "二值化应只有黑白两色")

    def test_invert(self):
        out = IU.invert(self.img)
        a = QColor.fromRgba(self.img.pixel(10, 5))
        b = QColor.fromRgba(out.pixel(10, 5))
        self.assertEqual(b.red(), 255 - a.red())
        self.assertEqual(b.green(), 255 - a.green())
        self.assertEqual(b.blue(), 255 - a.blue())

    def test_blur(self):
        self._assert_valid(IU.blur(self.img), "blur")

    def test_sharpen(self):
        self._assert_valid(IU.sharpen(self.img), "sharpen")

    def test_emboss(self):
        self._assert_valid(IU.emboss(self.img), "emboss")

    def test_canny(self):
        self._assert_valid(IU.canny(self.img), "canny")


class TestFloodFill(unittest.TestCase):
    def setUp(self):
        _qapp()

    def test_fill_region(self):
        # 左半黑右半白的图，从左侧填充红色应只影响左半
        img = make_image(40, 20, lambda x, y: (0, 0, 0) if x < 20 else (255, 255, 255))
        out = IU.flood_fill(img, QPoint(5, 5), QColor(255, 0, 0))
        left = QColor.fromRgba(out.pixel(5, 5))
        right = QColor.fromRgba(out.pixel(30, 5))
        self.assertEqual((left.red(), left.green(), left.blue()), (255, 0, 0))
        self.assertEqual((right.red(), right.green(), right.blue()), (255, 255, 255))

    def test_out_of_bounds(self):
        img = make_image(10, 10, lambda x, y: (0, 0, 0))
        self.assertIsNone(IU.flood_fill_mask(img, QPoint(99, 99)))

    def test_compat_positions(self):
        img = make_image(20, 10, lambda x, y: (0, 0, 0))
        positions = IU.floodFill(img, QPoint(5, 5))
        self.assertEqual(len(positions), 200)   # 整图连通


if __name__ == "__main__":
    unittest.main(verbosity=2)
