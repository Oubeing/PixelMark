# -*- coding: utf-8 -*-
"""UI 构建脚本：用 pyuic5 将 view/*.ui 编译为 view/*_ui.py。

用法：
    python tools/build_ui.py

生成物（请勿手改，重新生成会覆盖）：
    pixelmark/view/main_window_ui.py      <- MainWindow.ui
    pixelmark/view/base_adjust_ui.py      <- BaseAdjustDialog.ui
    pixelmark/view/scale_dialog_ui.py     <- ScaleDialog.ui
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYUIC = os.path.join(os.path.dirname(sys.executable), "pyuic5") if os.name == "nt" else "pyuic5"

TARGETS = [
    ("MainWindow.ui", "main_window_ui.py"),
    ("BaseAdjustDialog.ui", "base_adjust_ui.py"),
    ("ScaleDialog.ui", "scale_dialog_ui.py"),
]


def main():
    view_dir = os.path.join(ROOT, "pixelmark", "view")
    for src, dst in TARGETS:
        out = os.path.join(view_dir, dst)
        cmd = [sys.executable, "-m", "PyQt5.uic.pyuic",
               os.path.join(view_dir, src), "-o", out]
        print(" ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("FAILED:", src, r.stderr)
            return 1
        if r.stderr.strip():
            print("warn:", r.stderr.strip()[:400])
        # 统一头部注释
        with open(out, "r", encoding="utf-8") as f:
            code = f.read()
        banner = ("# -*- coding: utf-8 -*-\n"
                  "# 本文件由 tools/build_ui.py 自动生成，请勿手工编辑。\n"
                  "# 修改界面请编辑 pixelmark/view/%s 后重新运行 build_ui.py。\n\n" % src)
        # pyuic 会附加 import imgs_rc（资源模块名由 qrc 文件名推导）。
        # 本项目资源统一由 pixelmark.app 通过 pixelmark.resources 加载，故移除该行。
        code = "\n".join(line for line in code.splitlines()
                         if line.strip() != "import imgs_rc") + "\n"
        with open(out, "w", encoding="utf-8") as f:
            f.write(banner + code)
        print("OK ->", os.path.relpath(out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
