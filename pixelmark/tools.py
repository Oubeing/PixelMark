# -*- coding: utf-8 -*-
"""工具注册表：工具 ID、元数据与快捷键。"""

from enum import Enum


class ToolID(Enum):
    """画布工具标识。

    绘图类工具直接修改图像（可撤销）；测量标注类为叠加层，可随时删除。
    """

    # ---- 绘图 ----
    PEN = "pen"            # 画笔
    BUCKET = "bucket"      # 油漆桶
    LINE = "line"          # 直线
    RECT = "rect"          # 矩形
    ELLIPSE = "ellipse"    # 椭圆
    ERASE = "erase"        # 橡皮擦
    ARROW = "arrow"        # 箭头
    TEXT = "text"          # 文字
    PICKER = "picker"      # 取色器

    # ---- 测量标注（新增） ----
    CALIBRATE = "calibrate"    # 比例尺标定
    DISTANCE = "distance"      # 测距
    ANGLE = "angle"            # 测角
    AREA = "area"              # 测面积（矩形）
    RADIUS = "radius"          # 测圆
    SCALEBAR = "scalebar"      # 绘制比例尺图形
    ANNOT_ARROW = "annot_arrow"  # 箭头标注
    ANNOT_TEXT = "annot_text"    # 文字标注


# 工具元数据：名称 / 图标 / 分组 / 默认光标 / 快捷键
TOOLS = {
    ToolID.PEN:        dict(name="画笔", icon="pen", group="draw", cursor="cross", key="B"),
    ToolID.BUCKET:     dict(name="喷桶", icon="bucket", group="draw", cursor="cross", key="U"),
    ToolID.LINE:       dict(name="直线", icon="line", group="draw", cursor="cross", key="L"),
    ToolID.RECT:       dict(name="矩形", icon="rect", group="draw", cursor="cross", key="R"),
    ToolID.ELLIPSE:    dict(name="椭圆", icon="ellipse", group="draw", cursor="cross", key="O"),
    ToolID.ERASE:      dict(name="橡皮擦", icon="erase", group="draw", cursor="cross", key="E"),
    ToolID.ARROW:      dict(name="箭头", icon="arrow", group="draw", cursor="cross", key="A"),
    ToolID.TEXT:       dict(name="文字", icon="text", group="draw", cursor="ibeam", key="T"),
    ToolID.PICKER:     dict(name="取色", icon="picker", group="draw", cursor="pointing", key="I"),

    ToolID.CALIBRATE:  dict(name="标定比例尺", icon="calibrate", group="measure", cursor="cross", key="C"),
    ToolID.DISTANCE:   dict(name="测距", icon="distance", group="measure", cursor="cross", key="D"),
    ToolID.ANGLE:      dict(name="测角", icon="angle", group="measure", cursor="cross", key="G"),
    ToolID.AREA:       dict(name="测面积", icon="area", group="measure", cursor="cross", key="M"),
    ToolID.RADIUS:     dict(name="测圆", icon="radius", group="measure", cursor="cross", key="V"),
    ToolID.SCALEBAR:   dict(name="比例尺", icon="scalebar", group="measure", cursor="cross", key="S"),
    ToolID.ANNOT_ARROW: dict(name="箭头标注", icon="annotArrow", group="measure", cursor="cross", key="N"),
    ToolID.ANNOT_TEXT: dict(name="文字标注", icon="textNote", group="measure", cursor="ibeam", key="Y"),
}

# 拖拽类工具（按下-移动-释放）
DRAG_TOOLS = {
    ToolID.LINE, ToolID.RECT, ToolID.ELLIPSE, ToolID.ARROW,
    ToolID.CALIBRATE, ToolID.DISTANCE, ToolID.AREA, ToolID.RADIUS,
    ToolID.ANNOT_ARROW,
}
# 自由绘制类工具
FREEHAND_TOOLS = {ToolID.PEN, ToolID.ERASE}
# 单击即完成
CLICK_TOOLS = {ToolID.BUCKET, ToolID.TEXT, ToolID.ANNOT_TEXT, ToolID.PICKER}
# 单击放置整齐长度，也支持拖拽自定义长度
CLICK_OR_DRAG_TOOLS = {ToolID.SCALEBAR}
# 多次点击（多边形式）
MULTI_CLICK_TOOLS = {ToolID.ANGLE}
# 需要两点以上的拖拽测量（松开时弹出输入/结果）
MEASURE_TOOLS = {
    ToolID.CALIBRATE, ToolID.DISTANCE, ToolID.ANGLE, ToolID.AREA,
    ToolID.RADIUS, ToolID.ANNOT_ARROW,
}


def tool_name(tool):
    meta = TOOLS.get(tool)
    return meta["name"] if meta else str(tool)
