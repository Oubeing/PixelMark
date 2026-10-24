# -*- coding: utf-8 -*-
"""PixelMark 主窗口。

职责：装配菜单 / 工具栏 / 左侧工具面板 / 画布 / 测量面板 / 状态栏，
并把界面事件编排到 ``CanvasWidget``（绘图与测量交互）与各类对话框上。

功能版图：
- 绘图：9 个工具（画笔/喷桶/直线/矩形/椭圆/橡皮擦/箭头/文字/取色），
  颜色、粗细、填充、虚线、平滑、不透明度可调，统一撤销/重做；
- 测量标注：8 个工具（标定/测距/测角/测面积/测圆/比例尺/箭头标注/文字标注），
  支持整体移动、控制点调整、双击编辑文字；
- 图像处理：调节对话框 + 7 种滤镜 + 旋转翻转 + 图像信息；
- 视图：铺满绘图区（默认）/ 适应窗口 / 手动缩放，坐标与比例尺实时显示。
"""

import csv
import os

from PyQt5.QtCore import Qt, QEvent, QSize
from PyQt5.QtGui import QColor, QIcon, QImage, QKeySequence, QTransform
from PyQt5.QtWidgets import (QAction, QActionGroup, QButtonGroup, QCheckBox,
                             QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QHBoxLayout, QLabel, QMainWindow, QMenu,
                             QMessageBox, QPushButton, QRadioButton, QShortcut,
                             QSlider, QSpinBox, QToolBar, QVBoxLayout, QWidget)

from . import __app_name__, __version__
from .canvas import CanvasWidget
from .capture import CameraCaptureDialog, VideoFrameDialog
from .dialogs import AboutDialog, BaseAdjustDialog, HelpDialog, ScaleCalibrateDialog, TextInputDialog
from .measurement import UNIT_PRESETS, Scale
from .tools import TOOLS, ToolID, tool_name
from .util import imageutil as IU
from .util.errors import (ImageLoadError, ImageSaveError, ScaleError,
                          install_excepthook)
from .util.logging import get_logger
from .view.main_window_ui import Ui_MainWindow

logger = get_logger("main_window")

TOOL_BUTTONS = [
    ("penBtn", ToolID.PEN),
    ("bucketBtn", ToolID.BUCKET),
    ("lineBtn", ToolID.LINE),
    ("rectBtn", ToolID.RECT),
    ("ellipseBtn", ToolID.ELLIPSE),
    ("eraseButton", ToolID.ERASE),
    ("arrowBtn", ToolID.ARROW),
    ("textBtn", ToolID.TEXT),
    ("pickerBtn", ToolID.PICKER),
    ("calibrateBtn", ToolID.CALIBRATE),
    ("distanceBtn", ToolID.DISTANCE),
    ("angleBtn", ToolID.ANGLE),
    ("areaBtn", ToolID.AREA),
    ("radiusBtn", ToolID.RADIUS),
    ("scalebarBtn", ToolID.SCALEBAR),
    ("annotArrowBtn", ToolID.ANNOT_ARROW),
    ("annotTextBtn", ToolID.ANNOT_TEXT),
]

# 工具在菜单 / 工具栏中的固定顺序
DRAW_TOOLS_ORDER = [ToolID.PEN, ToolID.BUCKET, ToolID.LINE, ToolID.RECT,
                    ToolID.ELLIPSE, ToolID.ERASE, ToolID.ARROW, ToolID.TEXT,
                    ToolID.PICKER]
MEASURE_TOOLS_ORDER = [ToolID.CALIBRATE, ToolID.DISTANCE, ToolID.ANGLE,
                       ToolID.AREA, ToolID.RADIUS, ToolID.SCALEBAR,
                       ToolID.ANNOT_ARROW, ToolID.ANNOT_TEXT]

# 「工具选项」区各行的显隐规则：与当前工具联动，同屏可调
TOOLS_WITH_COLORS = {ToolID.PEN, ToolID.ERASE, ToolID.LINE, ToolID.RECT,
                     ToolID.ELLIPSE, ToolID.ARROW, ToolID.TEXT, ToolID.BUCKET}
TOOLS_WITH_PEN_SIZE = {ToolID.PEN, ToolID.ERASE, ToolID.LINE, ToolID.RECT,
                       ToolID.ELLIPSE, ToolID.ARROW}
TOOLS_WITH_FILL = {ToolID.RECT, ToolID.ELLIPSE, ToolID.ARROW}
TOOLS_WITH_DASH = {ToolID.PEN, ToolID.LINE, ToolID.RECT, ToolID.ELLIPSE,
                   ToolID.ARROW}
TOOLS_WITH_SMOOTH = {ToolID.PEN, ToolID.ERASE}

# 每个工具的使用提示（选项区常显 + 状态栏 transient 提示）
TOOL_HINTS = {
    ToolID.PEN: "画笔：左键拖拽绘制（前景色），右键背景色",
    ToolID.BUCKET: "喷桶：单击填充连通区域（左键前景色 / 右键背景色）",
    ToolID.LINE: "直线：拖拽绘制直线，可设置粗细 / 虚线",
    ToolID.RECT: "矩形：拖拽绘制矩形，可设置填充 / 虚线",
    ToolID.ELLIPSE: "椭圆：拖拽绘制椭圆，可设置填充 / 虚线",
    ToolID.ERASE: "橡皮擦：用背景色擦除，可调粗细",
    ToolID.ARROW: "箭头：拖拽绘制箭头",
    ToolID.TEXT: "文字：单击画布输入文字与字号",
    ToolID.PICKER: "取色：单击画布拾取颜色作为前景色",
    ToolID.CALIBRATE: "标定比例尺：拖一条已知长度的线，输入实际值",
    ToolID.DISTANCE: "测距：拖拽两点测量距离（松开显示结果）",
    ToolID.ANGLE: "测角：依次点击 起点→顶点→终点（右键取消）",
    ToolID.AREA: "测面积：拖出矩形测量边长与面积",
    ToolID.RADIUS: "测圆：从圆心拖出半径，测量 R/D/面积",
    ToolID.SCALEBAR: "比例尺图形：单击放整齐长度，拖拽自定义",
    ToolID.ANNOT_ARROW: "箭头标注：拖出箭头，松开后可输入文字",
    ToolID.ANNOT_TEXT: "文字标注：单击画布输入文字标注",
}

# 画布交互提示（标注可拖动调整，在任何工具下都生效）
ANNOT_HINT = "标注调整：左键拖动整体移动，拖控制点改形状，双击文字类标注编辑内容"


class PixelMarkWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self._current_path = None
        self._dirty = False
        self._adjust_dialog = None
        self._adjust_base = None

        self._init_tool_options()
        self._init_tool_group()
        self._init_tool_actions()
        self._init_extra_actions()
        self._rebuild_toolbar()
        self._init_display_units()
        self._init_status_bar()
        self._establishConnections()
        self._init_shortcuts()
        self._init_viewport_tracking()
        self._refresh_measure_list()
        self._refresh_scale_info()
        self._refresh_title()
        self._select_tool(ToolID.PEN)   # 同步选项区显隐与提示

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def showEvent(self, event):
        """窗口显示后按当前视口执行一次视图适配（铺满/适应窗口）。"""
        super().showEvent(event)
        self.board.refit_if_auto()

    def _init_tool_group(self):
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for obj_name, tool in TOOL_BUTTONS:
            btn = getattr(self, obj_name, None)
            if btn is None:
                logger.warning("UI 中缺少工具按钮: %s", obj_name)
                continue
            self.tool_buttons[tool] = btn
            self.tool_group.addButton(btn)
            btn.setChecked(tool == ToolID.PEN)
        self.board.tool = ToolID.PEN

    # ------------------------------------------------------------------
    # 工具选项区（与所选工具同屏显示，不再藏在折叠面板里）
    # ------------------------------------------------------------------
    def _init_tool_options(self):
        """在「工具选项」容器中构建属性行，按当前工具显隐。"""
        box = self.toolOptionsBox
        box.setStyleSheet("QLabel { font-size:11px; color:#444; }")

        def make_row(*widgets):
            w = QWidget(box)
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 1, 0, 1)
            h.setSpacing(4)
            for x in widgets:
                h.addWidget(x)
            h.addStretch(1)
            box.layout().addWidget(w)
            return w

        # 颜色行：前景色 / 背景色
        self.preColorBtn = QPushButton(box)
        self.preColorBtn.setObjectName("preColorBtn")
        self.preColorBtn.setFixedSize(40, 22)
        self.preColorBtn.setStyleSheet("background-color: #000000")
        self.preColorBtn.setToolTip("前景色（左键绘制颜色）")
        self.backColorBtn = QPushButton(box)
        self.backColorBtn.setObjectName("backColorBtn")
        self.backColorBtn.setFixedSize(40, 22)
        self.backColorBtn.setStyleSheet("background-color: #FFFFFF")
        self.backColorBtn.setToolTip("背景色（右键 / 橡皮擦颜色）")
        self.opt_colors_row = make_row(QLabel("颜色"), self.preColorBtn,
                                       self.backColorBtn)

        # 粗细行
        self.penSizeBtn = QComboBox(box)
        self.penSizeBtn.setObjectName("penSizeBtn")
        self.penSizeBtn.setFocusPolicy(Qt.ClickFocus)
        self.penSizeBtn.setEditable(True)
        self.penSizeBtn.setFixedHeight(22)
        self.penSizeBtn.setMinimumContentsLength(3)
        for s in (2, 4, 6, 8, 10, 12, 14, 20, 30):
            self.penSizeBtn.addItem(str(s))
        self.pxLabel = QLabel("px", box)
        self.opt_size_row = make_row(QLabel("粗细"), self.penSizeBtn,
                                     self.pxLabel)

        # 样式行：填充 / 虚线 / 平滑（按工具显隐）
        self.fillChk = QCheckBox("填充形状", box)
        self.fillChk.setObjectName("fillChk")
        self.fillChk.setToolTip("矩形/椭圆/箭头端点是否填充")
        self.dashChk = QCheckBox("虚线样式", box)
        self.dashChk.setObjectName("dashChk")
        self.dashChk.setToolTip("直线/形状使用虚线")
        self.smoothChk = QCheckBox("平滑笔迹", box)
        self.smoothChk.setObjectName("smoothChk")
        self.smoothChk.setChecked(True)
        self.smoothChk.setToolTip("自由绘制时插值平滑")
        self.opt_style_row = make_row(self.fillChk, self.dashChk,
                                      self.smoothChk)

        # 不透明度行
        self.opacitySlider = QSlider(Qt.Horizontal, box)
        self.opacitySlider.setObjectName("opacitySlider")
        self.opacitySlider.setFixedHeight(18)
        self.opacitySlider.setRange(10, 100)
        self.opacitySlider.setValue(100)
        self.opacitySlider.setToolTip("绘制不透明度")
        self.opacityLabel = QLabel("100%", box)
        self.opacityLabel.setObjectName("opacityLabel")
        self.opacityLabel.setMinimumWidth(32)
        self.opt_opacity_row = make_row(QLabel("不透明度"), self.opacitySlider,
                                        self.opacityLabel)

        # 当前工具提示（常显）
        self.toolHintLabel = QLabel("", box)
        self.toolHintLabel.setObjectName("toolHintLabel")
        self.toolHintLabel.setWordWrap(True)
        self.toolHintLabel.setStyleSheet("color:#555; font-size:11px;")
        self.toolHintLabel.setMinimumHeight(22)
        box.layout().addWidget(self.toolHintLabel)

    def _update_tool_options(self, tool):
        """按当前工具显隐选项行，保证调整项与工具同屏可感。"""
        has_colors = tool in TOOLS_WITH_COLORS
        self.opt_colors_row.setVisible(has_colors)
        self.opt_size_row.setVisible(tool in TOOLS_WITH_PEN_SIZE)
        self.fillChk.setVisible(tool in TOOLS_WITH_FILL)
        self.dashChk.setVisible(tool in TOOLS_WITH_DASH)
        self.smoothChk.setVisible(tool in TOOLS_WITH_SMOOTH)
        # 行显隐直接由工具集合推导（查询 Qt 显隐态会被父级状态干扰）
        self.opt_style_row.setVisible(
            tool in TOOLS_WITH_FILL or tool in TOOLS_WITH_DASH
            or tool in TOOLS_WITH_SMOOTH)
        self.opt_opacity_row.setVisible(has_colors)
        self.toolHintLabel.setText(TOOL_HINTS.get(tool, ""))

    # ------------------------------------------------------------------
    # 工具动作（菜单勾选 + 工具栏图标 + 快捷键，三处同步）
    # ------------------------------------------------------------------
    def _init_tool_actions(self):
        self.tool_actions = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        reuse = {ToolID.CALIBRATE: self.actionCalibrate,
                 ToolID.DISTANCE: self.actionDistance,
                 ToolID.ANNOT_TEXT: self.actionAnnotText}
        for tool in DRAW_TOOLS_ORDER + MEASURE_TOOLS_ORDER:
            meta = TOOLS[tool]
            act = reuse.get(tool)
            if act is None:
                act = QAction(QIcon(":/img/img/%s.png" % meta["icon"]),
                              meta["name"], self)
                act.setObjectName("actionTool_%s" % tool.value)
                act.setShortcut(QKeySequence(meta["key"]))
                act.setShortcutContext(Qt.WindowShortcut)
            act.setCheckable(True)
            act.setToolTip("%s（快捷键 %s）" % (meta["name"], meta["key"]))
            act.triggered.connect(lambda checked=False, t=tool: self._select_tool(t))
            group.addAction(act)
            self.tool_actions[tool] = act
        # 绘制菜单：全部绘图工具
        self.menuDraw.addActions([self.tool_actions[t] for t in DRAW_TOOLS_ORDER])
        # 测量菜单：工具动作置顶，重建菜单顺序
        measure_menu = self.menu_5
        measure_menu.clear()
        measure_menu.addActions([self.tool_actions[t] for t in MEASURE_TOOLS_ORDER])
        measure_menu.addSeparator()
        measure_menu.addAction(self.actionClearScale)
        measure_menu.addAction(self.actionClearMeasure)
        measure_menu.addSeparator()
        measure_menu.addAction(self.actionExportMeasure)
        measure_menu.addSeparator()
        measure_menu.addAction(self.actionToggleMeasureDock)

    # ------------------------------------------------------------------
    # 其他菜单动作：图像处理 / 视图 / 编辑
    # ------------------------------------------------------------------
    def _init_extra_actions(self):
        # ---- 图像处理（「图像」菜单 / 工具栏第二行 / 图像处理菜单同源） ----
        self.actionAdjust = QAction(
            QIcon(":/img/img/adjust.png"), "图像调节（亮度/对比度/饱和度/色调）", self)
        self.actionAdjust.setObjectName("actionAdjust")
        self.filter_actions = {}
        for name, text, fn, label, icon in (
                ("actionGray", "灰度化", IU.gray, "灰度化", "gray"),
                ("actionBinary", "二值化", IU.binaryzation, "二值化", "binary"),
                ("actionInvert", "反相", IU.invert, "反相", "invert"),
                ("actionEmboss", "浮雕", IU.emboss, "浮雕", "emboss"),
                ("actionCanny", "边缘检测", IU.canny, "边缘检测", "canny"),
                ("actionBlur", "模糊", IU.blur, "模糊", "blur"),
                ("actionSharpen", "锐化", IU.sharpen, "锐化", "sharpen")):
            act = QAction(QIcon(":/img/img/%s.png" % icon), text, self)
            act.setObjectName(name)
            act.triggered.connect(
                lambda checked=False, f=fn, l=label: self._apply_filter(f, l))
            self.filter_actions[name] = act
            setattr(self, name, act)   # 便于测试与外部按名访问
        filter_order = ("actionGray", "actionBinary", "actionInvert",
                        "actionEmboss", "actionCanny", "actionBlur",
                        "actionSharpen")
        # 旋转 / 翻转 / 图像信息：补图标（工具栏第二行图标式按钮用）
        self.actionClockWise.setIcon(QIcon(":/img/img/rotateCW.png"))
        self.actionAntiClockWise.setIcon(QIcon(":/img/img/rotateCCW.png"))
        self.actionVerFilp.setIcon(QIcon(":/img/img/flipV.png"))
        self.actionHorFilp.setIcon(QIcon(":/img/img/flipH.png"))
        self.actionImgInfo.setIcon(QIcon(":/img/img/info.png"))
        image_menu = self.menu_3
        image_menu.clear()
        image_menu.addAction(self.actionAdjust)
        image_menu.addSeparator()
        image_menu.addActions([self.filter_actions[n] for n in filter_order])
        image_menu.addSeparator()
        image_menu.addMenu(self.menu_4)
        image_menu.addAction(self.actionImgInfo)

        # ---- 视图 ----
        self.actionZoomFill = QAction(
            QIcon(":/img/img/zoomFill.png"), "铺满绘图区", self)
        self.actionZoomFill.setObjectName("actionZoomFill")
        self.actionZoomFill.setShortcut(QKeySequence("Ctrl+2"))
        self.actionZoomFill.setShortcutContext(Qt.WindowShortcut)
        self.actionZoomFill.setToolTip("缩放至铺满绘图区（边缘裁剪，无滚动条） (Ctrl+2)")
        self.actionToggleToolPanel = QAction("显示/隐藏左侧工具面板", self)
        self.actionToggleToolPanel.setObjectName("actionToggleToolPanel")
        self.actionToggleToolPanel.setCheckable(True)
        self.actionToggleToolPanel.setChecked(True)
        self.actionToggleToolBar = QAction("显示/隐藏工具栏", self)
        self.actionToggleToolBar.setObjectName("actionToggleToolBar")
        self.actionToggleToolBar.setCheckable(True)
        self.actionToggleToolBar.setChecked(True)
        self.actionToggleStatusBar = QAction("显示/隐藏状态栏", self)
        self.actionToggleStatusBar.setObjectName("actionToggleStatusBar")
        self.actionToggleStatusBar.setCheckable(True)
        self.actionToggleStatusBar.setChecked(True)
        view_menu = self.menu_view
        view_menu.clear()
        for act in (self.actionZoomIn, self.actionZoomOut,
                    self.actionZoomFit, self.actionZoomFill,
                    self.actionZoom100):
            view_menu.addAction(act)
        view_menu.addSeparator()
        for act in (self.actionToggleMeasureDock, self.actionToggleToolPanel,
                    self.actionToggleToolBar, self.actionToggleStatusBar):
            view_menu.addAction(act)

        # ---- 编辑 ----
        self.actionDeleteMeasure = QAction("删除所选测量标注", self)
        self.actionDeleteMeasure.setObjectName("actionDeleteMeasure")
        self.actionDeleteMeasure.setToolTip("删除测量列表中选中的标注（Delete）")
        self.menu_2.addSeparator()
        self.menu_2.addAction(self.actionDeleteMeasure)

    # ------------------------------------------------------------------
    # 工具栏：图标式全集（文件/获取/编辑/视图/全部工具/清除标注）
    # 第二行：图像变换（调节/滤镜/旋转翻转/图像信息，图标直选）
    # ------------------------------------------------------------------
    def _rebuild_toolbar(self):
        tb = self.mainToolBar
        tb.clear()
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setIconSize(QSize(18, 18))
        tb.setStyleSheet("QToolBar { border-bottom: 1px solid #D8DCE4; }")
        for act in (self.actionNew, self.actionOpenImg, self.actionSave):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self.actionCamera, self.actionVideo):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self.actionUndo, self.actionRedo):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self.actionClear, self.actionClearDraw):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self.actionZoomOut, self.actionZoomFit,
                    self.actionZoomFill, self.actionZoom100,
                    self.actionZoomIn):
            tb.addAction(act)
        tb.addSeparator()
        for t in DRAW_TOOLS_ORDER:
            tb.addAction(self.tool_actions[t])
        tb.addSeparator()
        for t in MEASURE_TOOLS_ORDER:
            tb.addAction(self.tool_actions[t])
        tb.addSeparator()
        tb.addAction(self.actionClearMeasure)

        # ---- 第二行工具栏：图像变换（不占左侧面板空间，不会引入面板滚动条） ----
        if getattr(self, "imageToolBar", None) is None:
            itb = QToolBar("图像变换", self)
            itb.setObjectName("imageToolBar")
            itb.setToolButtonStyle(Qt.ToolButtonIconOnly)
            itb.setIconSize(QSize(18, 18))
            itb.setFloatable(False)
            itb.setMovable(False)
            itb.setStyleSheet("QToolBar { border-bottom: 1px solid #D8DCE4; }")
            self.imageToolBar = itb
            itb.addWidget(self._image_toolbar_title())
            itb.addAction(self.actionAdjust)
            itb.addSeparator()
            for n in ("actionGray", "actionBinary", "actionInvert",
                      "actionEmboss", "actionCanny", "actionBlur", "actionSharpen"):
                itb.addAction(self.filter_actions[n])
            itb.addSeparator()
            for act in (self.actionClockWise, self.actionAntiClockWise,
                        self.actionVerFilp, self.actionHorFilp):
                itb.addAction(act)
            itb.addSeparator()
            itb.addAction(self.actionImgInfo)
            self.addToolBarBreak()
            self.addToolBar(Qt.TopToolBarArea, itb)

    def _image_toolbar_title(self):
        """图像变换工具栏的行标题。"""
        if getattr(self, "_image_toolbar_title_label", None) is None:
            lbl = QLabel(" 图像变换 ")
            lbl.setStyleSheet("font-weight:bold; color:#2E3440; font-size:11px;")
            self._image_toolbar_title_label = lbl
        return self._image_toolbar_title_label

    def _init_display_units(self):
        """显示单位下拉：跟随标定单位 + 常用长度单位。"""
        self._base_unit = None
        self.displayUnitCombo.clear()
        self.displayUnitCombo.addItem("跟随标定单位", None)
        for u in UNIT_PRESETS:
            self.displayUnitCombo.addItem(u, u)
        self.displayUnitCombo.setCurrentIndex(0)

    def _init_status_bar(self):
        sb = self.statusBar()
        sb.setStyleSheet("QStatusBar { border-top: 1px solid #D8DCE4; background: #F7F9FC; }"
                         "QStatusBar::item { border: none; }")
        self.lbl_coord = QLabel("X: -  Y: -")
        self.lbl_size = QLabel("画布: -")
        self.lbl_zoom = QLabel("缩放: 100%")
        self.lbl_scale = QLabel("比例尺: 未标定")
        self.lbl_tool = QLabel("工具: 画笔")
        for w in (self.lbl_coord, self.lbl_size, self.lbl_zoom, self.lbl_scale, self.lbl_tool):
            w.setStyleSheet("padding: 0 8px; color: #444;")
            sb.addPermanentWidget(w)
        self._refresh_size_label()
        self._refresh_zoom_label()

    def _init_viewport_tracking(self):
        """跟踪画布滚动区视口大小变化，自动适应窗口模式下实时缩放。"""
        viewport = self.scrollArea.viewport()
        viewport.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.scrollArea.viewport() and event.type() == QEvent.Resize:
            self.board.refit_if_auto()
        return super().eventFilter(obj, event)

    def _init_shortcuts(self):
        # 工具快捷键由工具动作（QAction）承载，与菜单/工具栏勾选状态联动
        sc_del = QShortcut(QKeySequence(Qt.Key_Delete), self)
        sc_del.setContext(Qt.ApplicationShortcut)
        sc_del.activated.connect(self.board.delete_selected)
        sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        sc_esc.setContext(Qt.ApplicationShortcut)
        sc_esc.activated.connect(self._cancel_current)

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------
    def _establishConnections(self):
        board = self.board
        # ---- 文件 ----
        self.actionNew.triggered.connect(self._new_image)
        self.actionOpenImg.triggered.connect(self._open_image)
        self.actionSave.triggered.connect(lambda: self._save(flatten=True))
        self.actionSaveAs.triggered.connect(lambda: self._save(flatten=True, ask=True))
        self.actionSaveRaw.triggered.connect(lambda: self._save(flatten=False, ask=True))
        self.actionExit.triggered.connect(self.close)
        # ---- 编辑 ----
        self.actionUndo.triggered.connect(self.board.undo)
        self.actionRedo.triggered.connect(self.board.redo)
        self.actionClear.triggered.connect(self._clear_all)
        self.actionClearDraw.triggered.connect(self.board.restore_original)
        # ---- 图像 ----
        self.actionClockWise.triggered.connect(lambda: self._rotate(90))
        self.actionAntiClockWise.triggered.connect(lambda: self._rotate(-90))
        self.actionVerFilp.triggered.connect(lambda: self._mirror(True, False))
        self.actionHorFilp.triggered.connect(lambda: self._mirror(False, True))
        self.actionImgInfo.triggered.connect(self._show_image_info)
        # ---- 图像处理（滤镜/调节动作在 _init_extra_actions 中统一连接） ----
        self.actionAdjust.triggered.connect(self._open_base_adjust)
        # ---- 画笔属性 ----
        self.preColorBtn.clicked.connect(self._choose_pre_color)
        self.backColorBtn.clicked.connect(self._choose_back_color)
        self.penSizeBtn.editTextChanged.connect(self._choose_pen_size)
        self.penSizeBtn.currentIndexChanged.connect(self._choose_pen_size)
        self.fillChk.toggled.connect(self._on_pen_options)
        self.dashChk.toggled.connect(self._on_pen_options)
        self.smoothChk.toggled.connect(self._on_pen_options)
        self.opacitySlider.valueChanged.connect(self._on_opacity)
        # ---- 工具 ----
        for tool, btn in self.tool_buttons.items():
            btn.clicked.connect(lambda checked=False, t=tool: self._select_tool(t))
        # ---- 测量 ----
        self.clearMeasureBtn.clicked.connect(self.board.clear_measurements)
        self.actionClearMeasure.triggered.connect(self.board.clear_measurements)
        self.actionClearScale.triggered.connect(self._clear_scale)
        self.actionExportMeasure.triggered.connect(self._export_measurements)
        self.exportMeasureBtn.clicked.connect(self._export_measurements)
        self.deleteMeasureBtn.clicked.connect(self.board.delete_selected)
        self.actionDeleteMeasure.triggered.connect(self.board.delete_selected)
        self.actionToggleMeasureDock.toggled.connect(self._toggle_measure_dock)
        self.measureDock.visibilityChanged.connect(self._on_dock_visibility)
        self.measureList.itemSelectionChanged.connect(self._on_measure_selected)
        # ---- 获取图像（工具栏 / 获取菜单） ----
        self.actionCamera.triggered.connect(self._capture_from_camera)
        self.actionVideo.triggered.connect(self._capture_from_video)
        # ---- 视图 / 缩放 ----
        self.actionZoomIn.triggered.connect(self.board.zoom_in)
        self.actionZoomOut.triggered.connect(self.board.zoom_out)
        self.actionZoomFit.triggered.connect(self.board.zoom_fit)
        self.actionZoomFill.triggered.connect(self.board.zoom_fill)
        self.actionZoom100.triggered.connect(self.board.zoom_reset)
        self.actionToggleToolPanel.toggled.connect(self._toggle_tool_panel)
        self.actionToggleToolBar.toggled.connect(self._toggle_tool_bar)
        self.actionToggleStatusBar.toggled.connect(self._toggle_status_bar)
        board.zoomChanged.connect(self._refresh_zoom_label)
        # ---- 画布信号 ----
        board.statusHint.connect(self._show_status)
        board.coordChanged.connect(self._update_coord)
        board.scaleChanged.connect(self._on_scale_changed)
        board.measurementsChanged.connect(self._refresh_measure_list)
        board.colorPicked.connect(self._on_color_picked)
        board.imageChanged.connect(self._on_image_changed)
        board.calibrateRequested.connect(self._on_calibrate_requested)
        # ---- 帮助 ----
        self.actionHelp.triggered.connect(self._show_help)
        self.actionAbout.triggered.connect(self._show_about)
        # ---- 测量面板（右侧停靠） ----
        self.clearAllMeasureBtn.clicked.connect(self.board.clear_measurements)
        self.locateMeasureBtn.clicked.connect(self._locate_selected_measure)
        self.displayUnitCombo.currentIndexChanged.connect(self._on_display_unit_changed)
        self.measureList.itemDoubleClicked.connect(self._locate_selected_measure)

    # ------------------------------------------------------------------
    # 工具选择
    # ------------------------------------------------------------------
    def _select_tool(self, tool):
        """选择工具：排他且不可取消——任何时刻有且只有一个工具处于选中态。

        除了依赖 QButtonGroup / QActionGroup 的排他性，这里再显式同步
        三处状态（面板按钮、菜单/工具栏动作、画布当前工具），确保点击
        已选中的工具不会把它取消选择。
        """
        for t, btn in self.tool_buttons.items():
            if t != tool:
                btn.setChecked(False)
        for t, act in self.tool_actions.items():
            if t != tool:
                act.setChecked(False)
        btn = self.tool_buttons.get(tool)
        if btn is not None:
            btn.setChecked(True)
        act = self.tool_actions.get(tool)
        if act is not None:
            act.setChecked(True)
        self.board.tool = tool
        self.board._pending = []
        self.board._active_measure = None
        meta = TOOLS.get(tool, {})
        cursor = {"cross": Qt.CrossCursor, "ibeam": Qt.IBeamCursor,
                  "pointing": Qt.PointingHandCursor}.get(meta.get("cursor"), Qt.CrossCursor)
        self.board.set_tool_cursor(cursor)
        self.lbl_tool.setText("工具: %s" % tool_name(tool))
        hint = TOOL_HINTS.get(tool, "")
        self.toolHintLabel.setText(hint)
        self._update_tool_options(tool)
        self._show_status(hint)

    def _cancel_current(self):
        self.board.cancel_interaction()

    # ------------------------------------------------------------------
    # 画笔属性
    # ------------------------------------------------------------------
    def _choose_pen_size(self):
        text = self.penSizeBtn.currentText().strip()
        try:
            size = int(float(text))
        except (ValueError, TypeError):
            size = 2
        size = max(1, min(200, size))
        self.board.pen_size = size
        if self.penSizeBtn.currentText() != str(size):
            self.penSizeBtn.setEditText(str(size))

    def _choose_pre_color(self):
        color = QColorDialog_get_color(self, self.board.pen_color, "选择前景色")
        if color is not None:
            self.board.pen_color = color
            self.preColorBtn.setStyleSheet("background-color:%s" % color.name())

    def _choose_back_color(self):
        color = QColorDialog_get_color(self, self.board.back_color, "选择背景色")
        if color is not None:
            self.board.back_color = color
            self.backColorBtn.setStyleSheet("background-color:%s" % color.name())

    def _on_color_picked(self, color):
        self.board.pen_color = color
        self.preColorBtn.setStyleSheet("background-color:%s" % color.name())

    def _on_pen_options(self):
        self.board.fill_shapes = self.fillChk.isChecked()
        self.board.dashed = self.dashChk.isChecked()
        self.board.smooth = self.smoothChk.isChecked()

    def _on_opacity(self, value):
        self.board.opacity = value / 100.0
        self.opacityLabel.setText("%d%%" % value)

    # ------------------------------------------------------------------
    # 文件操作
    # ------------------------------------------------------------------
    def _refresh_title(self):
        name = os.path.basename(self._current_path) if self._current_path else "未命名"
        self.setWindowTitle("%s%s - %s 像素标绘" % (name, "*" if self._dirty else "", __app_name__))

    def _on_image_changed(self):
        self._dirty = True
        self._refresh_title()
        self._refresh_size_label()
        self._refresh_zoom_label()
        self.actionUndo.setEnabled(self.board.can_undo())
        self.actionRedo.setEnabled(self.board.can_redo())

    def _new_image(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("新建画布")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("请设置新画布尺寸："))
        spin_w = QSpinBox()
        spin_h = QSpinBox()
        for s in (spin_w, spin_h):
            s.setRange(16, 10000)
        spin_w.setValue(self.board.image.width())
        spin_h.setValue(self.board.image.height())
        row = QHBoxLayout()
        row.addWidget(QLabel("宽"))
        row.addWidget(spin_w)
        row.addWidget(QLabel("高"))
        row.addWidget(spin_h)
        row.addStretch(1)
        layout.addLayout(row)
        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("背景：白色 / 背景色"))
        self._new_bg_white = QRadioButton("白色")
        self._new_bg_back = QRadioButton("背景色")
        self._new_bg_white.setChecked(True)
        bg_row.addWidget(self._new_bg_white)
        bg_row.addWidget(self._new_bg_back)
        bg_row.addStretch(1)
        layout.addLayout(bg_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec_() != QDialog.Accepted:
            return
        background = Qt.white if self._new_bg_white.isChecked() else self.board.back_color
        self._current_path = None
        self.board.new_image(spin_w.value(), spin_h.value(), background=background)
        self._dirty = False
        self._refresh_title()
        self._show_status("已新建画布 %dx%d" % (spin_w.value(), spin_h.value()))

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图像", "", "图像文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*)")
        if not path:
            return
        try:
            image = QImage(path)
            if image.isNull():
                raise ImageLoadError("无法解码图像文件（格式不支持或文件已损坏）")
        except Exception as exc:  # noqa: BLE001
            logger.exception("打开图像失败: %s", path)
            QMessageBox.critical(self, "打开失败", "无法打开图像：\n%s\n\n%s" % (path, exc))
            return
        self.board.load_image(image)
        self._current_path = path
        self._dirty = False
        self._refresh_title()
        self._show_status("已打开 %s（%dx%d）" % (os.path.basename(path), image.width(), image.height()))

    def _save(self, flatten=True, ask=False):
        if self.board.image.isNull():
            QMessageBox.warning(self, "保存失败", "画布为空，没有可保存的内容。")
            return
        path = self._current_path
        if ask or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "保存图像", path or "untitled.png",
                "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;所有文件 (*)")
            if not path:
                return
        image = self.board.flattened_image(with_measurements=flatten)
        try:
            ok = image.save(path)
            if not ok:
                raise ImageSaveError("Qt 拒绝写入（路径无效或格式不支持）")
        except Exception as exc:  # noqa: BLE001
            logger.exception("保存失败: %s", path)
            QMessageBox.critical(self, "保存失败", "保存图像时出错：\n%s\n\n%s" % (path, exc))
            return
        self._current_path = path
        self._dirty = False
        self._refresh_title()
        self._show_status("已保存 %s（%s）" % (os.path.basename(path),
                                              "含标注" if flatten else "不含标注"))

    def _clear_all(self):
        reply = QMessageBox.question(self, "清空画布", "确定要清空整个画布吗？（可撤销）",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.board.clear_all()
            self._show_status("已清空画布")

    # ------------------------------------------------------------------
    # 图像处理
    # ------------------------------------------------------------------
    def _rotate(self, deg):
        t = QTransform()
        t.rotate(deg)
        self.board.transform_image(lambda img: img.transformed(t))

    def _mirror(self, horizontal, vertical):
        self.board.transform_image(lambda img: img.mirrored(horizontal, vertical))

    def _apply_filter(self, func, name):
        self.board.apply_filter(func, name)

    def _open_base_adjust(self):
        if self.board.image.isNull():
            QMessageBox.warning(self, "图像调节", "画布为空，无法进行图像调节。")
            return
        if self._adjust_dialog is None:
            self._adjust_dialog = BaseAdjustDialog(self)
            self._adjust_dialog.dialogRejected.connect(self._adjust_rejected)
            self._adjust_dialog.dialogAccepted.connect(self._adjust_accepted)
            self._adjust_dialog.brightSliderReleased.connect(self._adjust_bright)
            self._adjust_dialog.warmSliderReleased.connect(self._adjust_warm)
            self._adjust_dialog.saturabilitySliderReleased.connect(self._adjust_saturation)
            self._adjust_dialog.contrastSliderReleased.connect(self._adjust_contrast)
        self._adjust_base = self.board.image.copy()
        self._adjust_dialog.show()
        self._adjust_dialog.raise_()

    def _adjust_bright(self, value):
        self.board.preview = None
        self._adjust_preview(lambda img: IU.adjustBright(img, value), "亮度")

    def _adjust_warm(self, value):
        self._adjust_preview(lambda img: IU.adjustWarm(img, value), "色调")

    def _adjust_saturation(self, value):
        self._adjust_preview(lambda img: IU.adjustSaturation(img, value), "饱和度")

    def _adjust_contrast(self, value):
        self._adjust_preview(lambda img: IU.adjustContrast(img, value), "对比度")

    def _adjust_preview(self, func, name):
        try:
            self.board.preview = func(self._adjust_base)
        except Exception as exc:  # noqa: BLE001
            logger.exception("调节预览失败: %s", name)
            self._show_status("%s调节失败: %s" % (name, exc))
            return
        self.board.update()

    def _adjust_accepted(self):
        if self.board.preview is not None and not self.board.preview.isNull():
            self.board.begin_action("image")
            self.board.image = self.board.preview
            self.board.imageChanged.emit()
        self.board.preview = None
        self.board.refresh()
        self._show_status("已应用图像调节")

    def _adjust_rejected(self):
        self.board.preview = None
        self.board.refresh()
        self._show_status("已取消图像调节")

    def _show_image_info(self):
        img = self.board.image
        if img.isNull():
            QMessageBox.information(self, "图像信息", "画布为空。")
            return
        QMessageBox.information(
            self, "图像信息",
            "尺寸：%d × %d 像素\n格式：%s\n当前缩放：%d%%\n测量标注：%d 个\n比例尺：%s" % (
                img.width(), img.height(), self._format_name(img.format()),
                round(self.board.zoom_percent()),
                len(self.board.measurements), self.board.scale.describe()))

    @staticmethod
    def _format_name(fmt):
        names = {
            QImage.Format_RGB32: "RGB32", QImage.Format_ARGB32: "ARGB32",
            QImage.Format_RGBA8888: "RGBA8888", QImage.Format_Grayscale8: "Grayscale8",
            QImage.Format_Indexed8: "Indexed8",
        }
        return names.get(fmt, str(fmt))

    # ------------------------------------------------------------------
    # 测量
    # ------------------------------------------------------------------
    def _refresh_scale_info(self):
        self.scaleInfoLabel.setText("当前比例尺："
                                    + self.board.scale.describe_compact())
        self.lbl_scale.setText("比例尺: " + ("%.4f %s/px" % (
            1.0 / self.board.scale.pixels_per_unit, self.board.scale.unit)
            if self.board.scale.calibrated else "未标定"))

    def _on_scale_changed(self, _desc):
        self._refresh_scale_info()
        # 首个已标定的比例尺作为基准单位（后续显示单位切换不影响它）
        if self.board.scale.calibrated and not getattr(self, "_base_unit", None):
            self._base_unit = self.board.scale.unit
        # 同步显示单位下拉：当前单位即标定单位时选中"跟随"，否则选中对应单位
        unit = self.board.scale.unit
        base = getattr(self, "_base_unit", None)
        self.displayUnitCombo.blockSignals(True)
        if unit == base:
            self.displayUnitCombo.setCurrentIndex(0)
        else:
            idx = self.displayUnitCombo.findData(unit)
            self.displayUnitCombo.setCurrentIndex(idx if idx > 0 else 0)
        self.displayUnitCombo.blockSignals(False)

    def _clear_scale(self):
        if not self.board.scale.calibrated:
            self._show_status("当前未标定比例尺")
            return
        self._base_unit = None
        self.board.clear_scale()
        self._show_status("已清除比例标定")

    def _on_calibrate_requested(self, p1, p2, px_len):
        if px_len <= 0:
            QMessageBox.information(self, "标定比例尺",
                                    "请先拖出一条已知实际长度的线段。\n\n"
                                    "提示：选择「标定比例尺」工具后在图像上拖拽。")
            return
        dlg = ScaleCalibrateDialog(self, pixel_length=px_len, current=self.board.scale)
        if dlg.exec_():
            try:
                scale = dlg.result_scale()
            except ScaleError as exc:
                QMessageBox.warning(self, "标定失败", str(exc))
                return
            self.board.set_scale(scale)
            self._base_unit = scale.unit   # 记录标定基准单位
            # 标定线也作为测量保留（删除它不影响标定结果）
            from .measurement import make_calibrate
            self.board.add_measurement(make_calibrate(p1, p2))
            self._show_status("比例尺已标定：" + scale.describe())

    def _refresh_measure_list(self):
        self.measureList.clear()
        scale = self.board.scale
        for i, m in enumerate(self.board.measurements, 1):
            from PyQt5.QtWidgets import QListWidgetItem
            item = QListWidgetItem("%d. %s" % (i, m.title(scale)))
            item.setData(Qt.UserRole, i - 1)
            self.measureList.addItem(item)
        has = bool(self.board.measurements)
        self.actionExportMeasure.setEnabled(has)
        self.exportMeasureBtn.setEnabled(has)
        self.deleteMeasureBtn.setEnabled(has)
        self.locateMeasureBtn.setEnabled(has)
        self.clearAllMeasureBtn.setEnabled(has)
        self.actionClearMeasure.setEnabled(has)
        self.actionDeleteMeasure.setEnabled(has)

    def _on_measure_selected(self):
        items = self.measureList.selectedItems()
        if not items:
            self.board.selected = None
            self.board.update()
            return
        idx = items[0].data(Qt.UserRole)
        if idx is not None and 0 <= idx < len(self.board.measurements):
            self.board.selected = self.board.measurements[idx]
            self.board.update()

    def _toggle_measure_dock(self, visible):
        self.measureDock.setVisible(visible)

    def _toggle_tool_panel(self, visible):
        self.toolPanel.setVisible(visible)

    def _toggle_tool_bar(self, visible):
        self.mainToolBar.setVisible(visible)
        self.imageToolBar.setVisible(visible)

    def _toggle_status_bar(self, visible):
        self.statusBar().setVisible(visible)

    def _on_dock_visibility(self, visible):
        """用户通过标题栏关闭面板时同步菜单勾选状态。"""
        self.actionToggleMeasureDock.setChecked(visible)

    def _export_measurements(self):
        if not self.board.measurements:
            QMessageBox.information(self, "导出测量数据", "当前没有测量数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出测量数据", "measurements.csv", "CSV 文件 (*.csv);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["序号", "类型", "点坐标(图像像素)", "像素值", "实际值", "标注"])
                for i, m in enumerate(self.board.measurements, 1):
                    writer.writerow(m.csv_row(i, self.board.scale))
                writer.writerow([])
                writer.writerow(["比例尺", self.board.scale.describe()])
        except OSError as exc:
            logger.exception("导出 CSV 失败")
            QMessageBox.critical(self, "导出失败", "无法写入文件：\n%s" % exc)
            return
        self._show_status("已导出测量数据到 %s" % path)

    # ------------------------------------------------------------------
    # 获取图像：摄像头 / 视频截帧
    # ------------------------------------------------------------------
    def _capture_from_camera(self):
        try:
            dlg = CameraCaptureDialog(self)
        except ImageLoadError as exc:
            QMessageBox.warning(self, "摄像头不可用", str(exc))
            return
        dlg.captured.connect(self._load_captured_image)
        dlg.exec_()

    def _capture_from_video(self):
        try:
            dlg = VideoFrameDialog(self)
        except ImageLoadError as exc:
            QMessageBox.warning(self, "视频功能不可用", str(exc))
            return
        dlg.captured.connect(self._load_captured_image)
        dlg.exec_()

    def _load_captured_image(self, image):
        """把拍照/截帧得到的图像载入画布（保留撤销能力）。"""
        if image is None or image.isNull():
            return
        self.board.load_image(image)
        self._current_path = None
        self._dirty = False
        self._refresh_title()
        self._show_status("已载入图像（%dx%d）" % (image.width(), image.height()))

    # ------------------------------------------------------------------
    # 视图 / 缩放
    # ------------------------------------------------------------------
    def _refresh_zoom_label(self, _zoom=None):
        board = self.board
        if board.auto_fit:
            mode = "铺满" if board.fit_mode == "cover" else "适应窗口"
        else:
            mode = "手动"
        self.lbl_zoom.setText("缩放: %d%%（%s）" % (round(board.zoom_percent()), mode))

    def _locate_selected_measure(self):
        items = self.measureList.selectedItems()
        if not items:
            self._show_status("请先在测量列表中选择要定位的标注")
            return
        idx = items[0].data(Qt.UserRole)
        if idx is None or not (0 <= idx < len(self.board.measurements)):
            return
        self.board.locate_measurement(self.board.measurements[idx])
        self._show_status("已定位所选测量标注")

    def _on_display_unit_changed(self, _index=None):
        unit = self.displayUnitCombo.currentData()
        if unit is None:
            # 跟随标定单位：恢复标定时的原始单位
            base = getattr(self, "_base_unit", None)
            scale = self.board.scale
            if base and scale.calibrated and scale.unit != base:
                self.board.set_scale(scale.convert_to(base))
                self._show_status("显示单位已恢复为标定单位 %s" % base)
            return
        scale = self.board.scale
        if not scale.calibrated:
            self._show_status("尚未标定比例尺，显示单位将在标定后生效")
            return
        converted = scale.convert_to(unit)
        if converted is scale:
            self._show_status("无法换算到该单位（像素单位不可换算）")
            return
        self.board.set_scale(converted)
        self._show_status("显示单位已切换为 %s" % unit)

    # ------------------------------------------------------------------
    # 状态栏 / 杂项
    # ------------------------------------------------------------------
    def _show_status(self, text, timeout=6000):
        self.statusBar().showMessage(text, timeout)

    def _update_coord(self, x, y):
        self.lbl_coord.setText("X: %d  Y: %d" % (x, y))

    def _refresh_size_label(self):
        img = self.board.image
        if not img.isNull():
            self.lbl_size.setText("画布: %d×%d" % (img.width(), img.height()))

    def _show_help(self):
        HelpDialog(self).exec_()

    def _show_about(self):
        AboutDialog(self).exec_()

    # ------------------------------------------------------------------
    # 关闭保护
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, "退出确认", "当前图像尚未保存，是否先保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save)
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Save:
                self._save(flatten=True)
                if self._dirty:  # 保存被取消
                    event.ignore()
                    return
        event.accept()


def QColorDialog_get_color(parent, initial, title):
    """带取消处理的颜色选择（取消时保持原色，不写入无效值）。"""
    from PyQt5.QtWidgets import QColorDialog
    color = QColorDialog.getColor(initial, parent, title)
    if color is not None and color.isValid():
        return color
    return None
