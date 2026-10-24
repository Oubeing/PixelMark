# -*- coding: utf-8 -*-
"""一键运行全部测试。

用法（项目根目录）：
    python tools/run_tests.py

说明：无头（offscreen）环境下 PyQt5 在解释器退出时可能存在已知的段错误问题，
与测试逻辑无关；测试全部完成后用 os._exit 显式退出以规避。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TEST_MODULES = [
    "tests.test_measurement",
    "tests.test_imageutil",
    "tests.test_capture",
    "tests.test_icons",
    "tests.test_headless_ui",
]


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for mod in TEST_MODULES:
        if mod == "tests.test_headless_ui":
            continue  # 该脚本型测试在下方单独执行
        try:
            suite.addTests(loader.loadTestsFromName(mod))
        except Exception as exc:  # noqa: BLE001
            print("无法加载测试模块 %s: %s" % (mod, exc))
            return 2
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    print()
    print("== 无头 UI 功能测试 ==")
    from tests import test_headless_ui
    ui_code = test_headless_ui.main()

    print()
    print("总计: 单元测试 运行 %d, 失败 %d, 错误 %d；UI 测试 %s" % (
        result.testsRun, len(result.failures), len(result.errors),
        "通过" if ui_code == 0 else "失败"))
    code = 0 if (result.wasSuccessful() and ui_code == 0) else 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)   # 规避无头 Qt 退出段错误


if __name__ == "__main__":
    main()
