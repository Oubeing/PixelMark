# -*- coding: utf-8 -*-
"""图标尺寸一致性测试：所有图标内容包围盒归一化到统一大小。

开发时通过 ``python tools/make_icons.py`` 重新生成/归一化图标，
本测试守住「同一渲染尺寸下视觉大小一致」这一约束。
"""

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "img")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

TARGET = 136   # make_icons.py 中的归一化目标边长
TOLERANCE = 2  # 允许 LANCZOS 重采样带来 ±2px 误差


@unittest.skipUnless(HAS_PIL, "未安装 Pillow，跳过图标测试")
class IconUniformityTest(unittest.TestCase):

    def _icons(self):
        names = [f for f in os.listdir(IMG_DIR) if f.lower().endswith(".png")]
        self.assertTrue(names, "img/ 目录下没有 PNG 图标")
        return sorted(names)

    def test_all_icons_have_content(self):
        for name in self._icons():
            im = Image.open(os.path.join(IMG_DIR, name)).convert("RGBA")
            self.assertIsNotNone(im.split()[3].getbbox(),
                                 "%s 内容为空（全透明）" % name)

    def test_content_max_dimension_uniform(self):
        """所有图标内容最大边长一致（视觉大小一致的核心约束）。"""
        sizes = {}
        for name in self._icons():
            im = Image.open(os.path.join(IMG_DIR, name)).convert("RGBA")
            bbox = im.split()[3].getbbox()
            cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
            sizes[name] = max(cw, ch)
            self.assertAlmostEqual(
                max(cw, ch), TARGET, delta=TOLERANCE,
                msg="%s 内容最大边 %d 与目标 %d 不一致" % (name, max(cw, ch), TARGET))
        # 同一目标值（去重后应只有一个尺寸）
        self.assertEqual(len(set(sizes.values())), 1,
                         "图标内容尺寸不统一: %s" % sizes)

    def test_icons_centered_on_canvas(self):
        """所有图标在画布中居中（上下左右留白一致）。"""
        for name in self._icons():
            im = Image.open(os.path.join(IMG_DIR, name)).convert("RGBA")
            bbox = im.split()[3].getbbox()
            left, right = bbox[0], im.width - bbox[2]
            top, bottom = bbox[1], im.height - bbox[3]
            self.assertLessEqual(abs(left - right), TOLERANCE + 1,
                                 "%s 水平未居中（左 %d 右 %d）" % (name, left, right))
            self.assertLessEqual(abs(top - bottom), TOLERANCE + 1,
                                 "%s 垂直未居中（上 %d 下 %d）" % (name, top, bottom))


if __name__ == "__main__":
    unittest.main()
