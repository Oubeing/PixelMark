# -*- coding: utf-8 -*-
"""对话框集合：文字输入、比例尺标定、图像调节、帮助与关于。"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QTextBrowser, QTextEdit,
                             QVBoxLayout)

from . import __version__
from .measurement import Scale
from .util.errors import ScaleError
from .util.logging import get_logger
from .view.base_adjust_ui import Ui_baseAdjustDialog
from .view.scale_dialog_ui import Ui_ScaleDialog

logger = get_logger("dialogs")


# ---------------------------------------------------------------------------
# 文字输入对话框（文字工具 / 文字标注 / 箭头标注共用）
# ---------------------------------------------------------------------------

class TextInputDialog(QDialog):
    """多行文字 + 字号输入。"""

    def __init__(self, parent=None, title="输入文字", placeholder="请输入文字内容（Ctrl+Enter 确认）"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("文字内容："))
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlainText("")
        self.text_edit.setPlaceholderText(placeholder)
        layout.addWidget(self.text_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("字号："))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 200)
        self.size_spin.setValue(16)
        row.addWidget(self.size_spin)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.text_edit.setFocus()

    def values(self):
        return self.text_edit.toPlainText(), self.size_spin.value()


# ---------------------------------------------------------------------------
# 比例尺标定对话框
# ---------------------------------------------------------------------------

class ScaleCalibrateDialog(QDialog, Ui_ScaleDialog):
    """由测量线段像素长度 + 用户输入的实际长度构造 Scale。"""

    def __init__(self, parent=None, pixel_length=0.0, current=None):
        super().__init__(parent)
        self.setupUi(self)
        # 自定义单位输入长度限制（QComboBox 无 setMaxLength，限制其行编辑器）
        self.unitCombo.lineEdit().setMaxLength(12)
        self.pixel_length = float(pixel_length)
        self.measuredPxLabel.setText("%.2f px" % self.pixel_length)
        if current is not None and current.calibrated:
            self.realLenSpin.setValue(current.pixels_per_unit and
                                      self.pixel_length / current.pixels_per_unit or 10.0)
            self._set_unit(current.unit)
        else:
            self._set_unit("mm")
        self.realLenSpin.valueChanged.connect(self._update_preview)
        self.unitCombo.editTextChanged.connect(self._update_preview)
        self._update_preview()

    def _set_unit(self, unit):
        idx = self.unitCombo.findText(unit)
        if idx >= 0:
            self.unitCombo.setCurrentIndex(idx)
        else:
            self.unitCombo.setEditText(unit)

    def _update_preview(self):
        real = self.realLenSpin.value()
        if real > 0 and self.pixel_length > 0:
            self.previewLabel.setText("1 px = %.6g %s" % (
                real / self.pixel_length, self.unitCombo.currentText().strip()))

    def result_scale(self):
        """返回 Scale；输入非法时抛出 ScaleError。"""
        unit = self.unitCombo.currentText().strip()
        if not unit:
            raise ScaleError("单位不能为空")
        return Scale.from_lengths(self.pixel_length, self.realLenSpin.value(), unit)


# ---------------------------------------------------------------------------
# 图像调节对话框（亮度/对比度/饱和度/色调）
# ---------------------------------------------------------------------------

class BaseAdjustDialog(QDialog, Ui_baseAdjustDialog):

    brightSliderReleased = pyqtSignal(object)
    warmSliderReleased = pyqtSignal(object)
    saturabilitySliderReleased = pyqtSignal(object)
    contrastSliderReleased = pyqtSignal(object)

    dialogRejected = pyqtSignal()
    dialogAccepted = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.sliders = [self.brightSlider, self.saturabilitySlider,
                        self.contrastSlider, self.warmSlider]
        self.sliderLabels = [self.brightLabel, self.saturabilityLabel,
                             self.contrastLabel, self.warmLabel]
        self._establishConnections()

    def _establishConnections(self):
        self.dialogBtnBox.accepted.connect(self._dialogAccepted)
        self.dialogBtnBox.rejected.connect(self._dialogRejected)
        for slider in self.sliders:
            slider.valueChanged.connect(lambda v, s=slider: self._sliderValueChanged(s))
        self.brightSlider.sliderReleased.connect(self._brightSliderReleased)
        self.warmSlider.sliderReleased.connect(self._warmSliderReleased)
        self.saturabilitySlider.sliderReleased.connect(self._saturabilitySliderReleased)
        self.contrastSlider.sliderReleased.connect(self._contrastSliderReleased)

    def _sliderValueChanged(self, slider):
        try:
            idx = self.sliders.index(slider)
            self.sliderLabels[idx].setNum(slider.value())
        except ValueError:
            pass

    def _brightSliderReleased(self):
        v = self.brightSlider.value()
        self.brightLabel.setNum(v)
        self.brightSliderReleased.emit(v)

    def _contrastSliderReleased(self):
        v = self.contrastSlider.value()
        self.contrastLabel.setNum(v)
        self.contrastSliderReleased.emit(v)

    def _warmSliderReleased(self):
        v = self.warmSlider.value()
        self.warmLabel.setNum(v)
        self.warmSliderReleased.emit(v)

    def _saturabilitySliderReleased(self):
        v = self.saturabilitySlider.value()
        self.saturabilityLabel.setNum(v)
        self.saturabilitySliderReleased.emit(v)

    def _dialogAccepted(self):
        self.dialogAccepted.emit()

    def _dialogRejected(self):
        self.dialogRejected.emit()


# ---------------------------------------------------------------------------
# 帮助 / 关于
# ---------------------------------------------------------------------------

HELP_TEXT = """
<h2>PixelMark 像素标绘 · 使用说明</h2>
<h3>界面布局</h3>
<ul>
<li><b>左侧工具面板</b>（平铺常显，无折叠）：绘图工具、<b>工具选项</b>、测量标注、图像处理四个分区，
在矮窗口下整页滚动，所有入口始终可达。</li>
<li><b>工具选项区</b>随当前工具联动：选画笔显示粗细/颜色/平滑，选矩形显示填充/虚线，
选测量工具显示该工具的使用提示——调整项与工具同屏，不用去别处翻找。</li>
<li><b>工具栏</b>（图标式全集）：新建/打开/保存、摄像头/视频截帧、撤销/重做、清空/还原、
缩放五档、全部 17 个工具、清除测量标注；空间不足时末尾出现扩展按钮（»）。</li>
<li><b>菜单栏</b>：文件 / 编辑 / 绘制 / 图像 / 获取 / 视图 / 测量 / 帮助，
菜单项与工具栏、左侧面板同入口，工具菜单带勾选状态。</li>
<li>「视图」菜单可分别显示/隐藏：测量面板、左侧工具面板、工具栏、状态栏。</li>
</ul>
<h3>视图缩放</h3>
<ul>
<li>导入图像后自动<b>铺满绘图区</b>：图像缩放至覆盖整个绘图区、居中裁剪边缘，
画布与绘图区等大——<b>不出现滚动条、不留边缘空白</b>；窗口最大化 / 还原时自动重新计算。</li>
<li>工具栏或「视图」菜单：放大 / 缩小 / <b>适应窗口</b> / <b>铺满绘图区</b> / 原始大小。</li>
<li><b>适应窗口</b>（Ctrl+0）保证整图完整可见（小图不放大）；
<b>铺满绘图区</b>（Ctrl+2）填满绘图区，被裁剪的边缘可切回适应窗口或缩小查看。</li>
<li>手动缩放（Ctrl+= / Ctrl+- / Ctrl+滚轮、原始大小）退出自动模式，正常出现滚动条；
中键拖拽平移。</li>
<li>状态栏实时显示当前缩放比例与视图模式（铺满 / 适应窗口 / 手动）；
缩放不影响测量数值（始终按像素计算）。</li>
</ul>
<h3>绘图</h3>
<ul>
<li><b>画笔 / 喷桶 / 直线 / 矩形 / 椭圆 / 橡皮擦</b>：左键用前景色、右键用背景色绘制。</li>
<li><b>箭头 / 文字</b>：新增工具。文字工具单击画布后输入内容与字号。</li>
<li><b>取色</b>：单击画布拾取颜色为前景色。</li>
<li>「工具选项」区可设置：粗细、前景/背景色、形状填充、虚线、平滑笔迹、不透明度，
按当前工具自动显隐。</li>
</ul>
<h3>获取图像</h3>
<ul>
<li><b>摄像头拍照</b>（工具栏 / 获取 → 摄像头拍照）：选择设备实时预览，点击"拍照并载入画布"。</li>
<li><b>从视频获取照片</b>（工具栏 / 获取 → 视频截帧）：打开视频文件后可逐帧步进/播放，
拖动进度条定位，截取当前帧载入画布，也可保存为图片。</li>
</ul>
<h3>测量标注（叠加层，不破坏原图，可删除）</h3>
<ol>
<li><b>标定比例尺</b>：选择"标定比例尺"，在图像上已知长度的对象上画一条线，
输入实际长度与单位（如 10 mm）。标定后所有测量同时显示像素值与实际值。</li>
<li><b>测距</b>：拖拽两点，显示距离。</li>
<li><b>测角</b>：依次点击 起点 → 顶点 → 终点，显示角度。</li>
<li><b>测面积</b>：拖出矩形，显示边长与面积。</li>
<li><b>测圆</b>：从圆心拖出半径，显示 R/D/面积。</li>
<li><b>比例尺图形</b>：单击放置整齐长度的比例尺，或拖拽自定义长度。</li>
<li><b>箭头标注 / 文字标注</b>：带引线的说明标注。</li>
</ol>
<p>「显示单位」下拉可在 mm/cm/m/μm/in 之间切换（自动换算，不改变标定关系）；
选择"跟随标定单位"恢复标定时的单位。</p>
<p>测量结果会列在右侧"测量标注列表"中：<b>删除所选</b>、<b>清除全部标注</b>、
<b>定位所选</b>（滚动到该标注并高亮）、<b>导出 CSV</b>。
保存时默认包含标注，也可另存为"不含标注"的原始图像。</p>
<h3>快捷键</h3>
<p>Ctrl+N 新建 · Ctrl+O 打开 · Ctrl+S 保存 · Ctrl+Z 撤销 · Ctrl+Shift+Z/Ctrl+Y 重做 ·
Delete 删除所选测量 · Esc 取消当前操作 · F1 帮助</p>
<p>工具快捷键：B 画笔 U 喷桶 L 直线 R 矩形 O 椭圆 E 橡皮擦 A 箭头 T 文字 I 取色 ·
C 标定 D 测距 G 测角 M 面积 V 测圆 S 比例尺 N 箭头标注 Y 文字标注</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(HELP_TEXT)
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 PixelMark")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        title = QLabel("<h2>PixelMark 像素标绘 v%s</h2>" % __version__)
        layout.addWidget(title)
        body = QLabel(
            "<p>绘图 · 标注 · 测量一体化工作台</p>"
            "<p>技术栈：Python + PyQt5 + qtDesigner + OpenCV + numpy</p>"
            "<p>集绘图、标注与测量于一体：涵盖画笔/喷桶/直线/矩形/椭圆/橡皮擦/"
            "箭头/文字/取色等绘图工具，灰度/二值化/反相/浮雕/边缘/模糊/锐化等图像"
            "处理，以及测距、测角、测面积、测圆、比例尺标注等测量能力，"
            "并支持撤销重做、摄像头拍照、视频截帧、视图缩放与单位换算。</p>")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        layout.addWidget(body)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
