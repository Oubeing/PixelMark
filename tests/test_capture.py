# -*- coding: utf-8 -*-
"""图像获取（摄像头/视频）与比例尺单位的单元测试。

纯函数部分不依赖 GUI；涉及 QImage 的用例由 conftest 风格的前置
QApplication 保证（Qt 离屏 QImage 需要 QApplication 存在）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from pixelmark.measurement import (UNIT_TO_MM, Scale, convert_length,
                                   nice_scalebar_pixels, unit_to_mm_factor)

_app = QApplication.instance() or QApplication([])


class TestUnitConversion(unittest.TestCase):
    def test_factors(self):
        self.assertEqual(unit_to_mm_factor("mm"), 1.0)
        self.assertEqual(unit_to_mm_factor("cm"), 10.0)
        self.assertEqual(unit_to_mm_factor("m"), 1000.0)
        self.assertAlmostEqual(unit_to_mm_factor("in"), 25.4)
        self.assertIsNone(unit_to_mm_factor("px"))
        self.assertIsNone(unit_to_mm_factor("unknown"))

    def test_convert_length(self):
        self.assertAlmostEqual(convert_length(1, "m", "mm"), 1000.0)
        self.assertAlmostEqual(convert_length(100, "cm", "m"), 1.0)
        self.assertAlmostEqual(convert_length(1, "in", "mm"), 25.4)
        # 像素不可换算 -> 原值
        self.assertEqual(convert_length(5, "px", "mm"), 5)

    def test_scale_convert_to(self):
        s = Scale.from_lengths(300.0, 10.0, "mm")   # 300px = 10mm = 1cm
        cm = s.convert_to("cm")
        self.assertEqual(cm.unit, "cm")
        self.assertAlmostEqual(cm.pixels_per_unit, 300.0)    # 300 px/cm
        self.assertAlmostEqual(cm.to_unit(300.0), 1.0)       # 300px = 1cm
        # 同单位返回自身
        self.assertIs(s.convert_to("mm"), s)
        # 像素不可换算 -> 返回自身
        self.assertIs(s.convert_to("px"), s)
        # 未标定 -> 返回自身
        empty = Scale()
        self.assertIs(empty.convert_to("cm"), empty)

    def test_describe(self):
        s = Scale.from_lengths(300.0, 10.0, "mm")
        text = s.describe()
        self.assertIn("mm", text)
        self.assertIn("px", text)


class TestScalebarPixels(unittest.TestCase):
    def test_nice_values(self):
        for ppu in (0.5, 3.0, 30.0, 300.0):
            px = nice_scalebar_pixels(ppu)
            self.assertTrue(60 <= px <= 300, "%s -> %s" % (ppu, px))

    def test_invalid(self):
        self.assertEqual(nice_scalebar_pixels(0), 120.0)
        self.assertEqual(nice_scalebar_pixels(None), 120.0)


class TestCv2FrameConversion(unittest.TestCase):
    def test_frame_to_qimage(self):
        from pixelmark.capture import cv2_frame_to_qimage
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy 不可用")
        # 构造 BGR 帧（OpenCV 顺序）：蓝绿红渐变
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        frame[:, :, 0] = 200   # B
        frame[:, :, 1] = 100   # G
        frame[:, :, 2] = 50    # R
        img = cv2_frame_to_qimage(frame)
        self.assertFalse(img.isNull())
        self.assertEqual((img.width(), img.height()), (32, 24))
        rgb = img.pixel(0, 0)
        self.assertEqual((rgb >> 16) & 0xFF, 50)    # R
        self.assertEqual((rgb >> 8) & 0xFF, 100)    # G
        self.assertEqual(rgb & 0xFF, 200)           # B

    def test_none_frame_raises(self):
        from pixelmark.capture import cv2_frame_to_qimage
        from pixelmark.util.errors import ImageLoadError
        with self.assertRaises(ImageLoadError):
            cv2_frame_to_qimage(None)


if __name__ == "__main__":
    unittest.main()
