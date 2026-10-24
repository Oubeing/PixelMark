# -*- coding: utf-8 -*-
"""生成 PixelMark 工具与图像变换图标（200x200 黑色扁平风格）。

同时对所有图标做**尺寸归一化**：
按内容包围盒等比缩放至统一目标框并居中，保证同一渲染尺寸下
所有图标视觉大小一致（画布尺寸/留白不一时直接混用会显大小参差）。
"""
import math
import os
from PIL import Image, ImageDraw

SIZE = 200
INK = (26, 26, 26, 255)
W = 20  # 主笔画宽度
TARGET = 136  # 归一化后内容最大边长（占画布 68%）
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "img")


def canvas():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def line(d, pts, width=W, color=INK):
    d.line(pts, fill=color, width=width, joint="curve")
    # 圆角端点
    r = width / 2.0
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def arrow_head(d, tip, angle_deg, size=46, color=INK):
    a = math.radians(angle_deg)
    for da in (150, -150):
        b = a + math.radians(da)
        line(d, [(tip[0], tip[1]),
                 (tip[0] + size * math.cos(b), tip[1] + size * math.sin(b))],
             width=int(W * 0.85), color=color)


def icon_arrow():
    im = canvas(); d = ImageDraw.Draw(im)
    line(d, [(38, 158), (152, 52)])
    arrow_head(d, (152, 52), math.degrees(math.atan2(52 - 158, 152 - 38)))
    return im


def icon_annot_arrow():
    """箭头标注：箭头 + 文字气泡"""
    im = canvas(); d = ImageDraw.Draw(im)
    line(d, [(52, 150), (128, 74)])
    arrow_head(d, (128, 74), math.degrees(math.atan2(74 - 150, 128 - 52)))
    d.rounded_rectangle([18, 22, 108, 66], radius=12, outline=INK, width=W)
    line(d, [(66, 66), (86, 92)], width=int(W * 0.8))  # 气泡引线
    line(d, [(34, 44), (92, 44)], width=10)            # 气泡内文字横线
    return im


def icon_text():
    im = canvas(); d = ImageDraw.Draw(im)
    line(d, [(48, 46), (152, 46)], width=26)
    line(d, [(100, 46), (100, 158)], width=24)
    line(d, [(72, 158), (128, 158)], width=24)
    return im


def icon_text_note():
    """文字标注：便签中的 T"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([26, 30, 174, 170], radius=16, outline=INK, width=W)
    line(d, [(66, 66), (134, 66)], width=18)
    line(d, [(100, 66), (100, 122)], width=16)
    line(d, [(82, 122), (118, 122)], width=16)
    line(d, [(60, 142), (140, 142)], width=12)
    return im


def icon_picker():
    im = canvas(); d = ImageDraw.Draw(im)
    # 滴管：斜置的管身 + 尖头 + 液滴
    d.polygon([(118, 30), (150, 62), (96, 130), (66, 100)], outline=INK, width=W)
    d.polygon([(66, 100), (96, 130), (52, 168), (30, 146)], fill=INK)
    d.ellipse([128, 148, 172, 192], fill=INK)
    return im


def _arc_arrow(im, d, a0, a1, head_at):
    d.arc([34, 34, 166, 166], start=a0, end=a1, fill=INK, width=W)
    # 箭头
    cx, cy, r = 100, 100, 66
    hx = cx + r * math.cos(math.radians(head_at))
    hy = cy + r * math.sin(math.radians(head_at))
    tangent = head_at + 90
    arrow_head(d, (hx, hy), tangent, size=44)


def icon_undo():
    im = canvas(); d = ImageDraw.Draw(im)
    _arc_arrow(im, d, 110, 350, 350)
    return im


def icon_redo():
    im = canvas(); d = ImageDraw.Draw(im)
    _arc_arrow(im, d, 190, 70, 70)
    return im


def icon_distance():
    """测距：斜置直尺 + 刻度"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 60, 170, 140], radius=10, outline=INK, width=W)
    for i, x in enumerate(range(52, 160, 18)):
        ln = 34 if i % 2 == 0 else 22
        line(d, [(x, 60), (x, 60 + ln)], width=9)
    line(d, [(48, 100), (152, 100)], width=8)
    return im


def icon_angle():
    im = canvas(); d = ImageDraw.Draw(im)
    line(d, [(36, 164), (104, 60)])
    line(d, [(104, 60), (168, 128)])
    d.arc([74, 60, 134, 120], start=250, end=350, fill=INK, width=12)
    d.ellipse([96, 52, 112, 68], fill=INK)
    return im


def icon_area():
    im = canvas(); d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 160, 160], outline=INK, width=W)
    for k in range(-120, 130, 34):
        d.line([(40 + k, 40), (40 + k + 120, 160)], fill=INK, width=9)
    return im


def icon_radius():
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([34, 34, 166, 166], outline=INK, width=W)
    line(d, [(100, 100), (158, 58)], width=14)
    d.ellipse([92, 92, 108, 108], fill=INK)
    return im


def icon_calibrate():
    """比例尺标定：带端挡的双向箭头"""
    im = canvas(); d = ImageDraw.Draw(im)
    line(d, [(48, 100), (152, 100)], width=16)
    arrow_head(d, (152, 100), 0, size=42)
    arrow_head(d, (48, 100), 180, size=42)
    line(d, [(40, 62), (40, 138)], width=16)
    line(d, [(160, 62), (160, 138)], width=16)
    return im


def icon_scalebar():
    """比例尺图形：黑白分段尺"""
    im = canvas(); d = ImageDraw.Draw(im)
    segs = [(30, 66, True), (66, 102, False), (102, 138, True), (138, 170, False)]
    for x0, x1, black in segs:
        d.rectangle([x0, 74, x1, 116], fill=INK if black else (0, 0, 0, 0),
                    outline=INK, width=10)
    line(d, [(30, 138), (30, 150)], width=10)
    line(d, [(100, 138), (100, 150)], width=10)
    line(d, [(170, 138), (170, 150)], width=10)
    return im


def icon_camera():
    """摄像头拍照：相机机身 + 镜头"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([26, 58, 174, 158], radius=18, outline=INK, width=W)
    d.rectangle([70, 36, 130, 62], outline=INK, width=14)      # 顶部取景器凸起
    d.ellipse([76, 76, 124, 124], outline=INK, width=14)       # 镜头外圈
    d.ellipse([92, 92, 108, 108], fill=INK)                    # 镜头中心
    d.ellipse([142, 72, 158, 88], fill=INK)                    # 快门指示灯
    return im


def icon_video():
    """视频截帧：胶片 + 播放三角"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([24, 56, 176, 148], radius=12, outline=INK, width=W)
    # 胶片齿孔
    for x in (44, 76, 108, 140, 168):
        d.rounded_rectangle([x - 7, 40, x + 7, 54], radius=3, fill=INK)
        d.rounded_rectangle([x - 7, 150, x + 7, 164], radius=3, fill=INK)
    d.polygon([(88, 82), (88, 122), (128, 102)], fill=INK)     # 播放三角
    return im


def icon_zoom_in():
    """放大：放大镜 + 加号"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([36, 36, 128, 128], outline=INK, width=W)
    line(d, [(128, 128), (166, 166)], width=int(W * 1.3))
    line(d, [(66, 82), (98, 82)], width=14)
    line(d, [(82, 66), (82, 98)], width=14)
    return im


def icon_zoom_out():
    """缩小：放大镜 + 减号"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([36, 36, 128, 128], outline=INK, width=W)
    line(d, [(128, 128), (166, 166)], width=int(W * 1.3))
    line(d, [(66, 82), (98, 82)], width=14)
    return im


def icon_zoom_fit():
    """适应窗口：外框 + 内敛箭头"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 34, 166, 166], radius=10, outline=INK, width=14)
    arrow_head(d, (54, 100), 180, size=34)
    arrow_head(d, (146, 100), 0, size=34)
    return im


def icon_zoom_fill():
    """填充窗口：外框 + 四角外扩箭头 + 中心实块（图像放大到覆盖边框）"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 34, 166, 166], radius=10, outline=INK, width=14)
    d.rectangle([78, 78, 122, 122], fill=INK)
    for tip, ang in (((60, 60), 225), ((140, 60), 315), ((60, 140), 135), ((140, 140), 45)):
        arrow_head(d, tip, ang, size=30)
    return im


def icon_zoom_100():
    """原始大小：1:1 方框"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 34, 166, 166], radius=10, outline=INK, width=14)
    d.rectangle([70, 70, 130, 130], outline=INK, width=12)
    return im


def icon_locate():
    """定位：十字准星"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 160, 160], outline=INK, width=14)
    line(d, [(100, 18), (100, 62)], width=14)
    line(d, [(100, 138), (100, 182)], width=14)
    line(d, [(18, 100), (62, 100)], width=14)
    line(d, [(138, 100), (182, 100)], width=14)
    d.ellipse([88, 88, 112, 112], fill=INK)
    return im


def icon_trash():
    """清除全部：垃圾桶"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rectangle([48, 62, 152, 168], outline=INK, width=W)
    line(d, [(36, 62), (164, 62)], width=18)
    line(d, [(82, 40), (118, 40)], width=16)
    line(d, [(88, 40), (94, 62)], width=12)
    line(d, [(112, 40), (106, 62)], width=12)
    line(d, [(84, 88), (84, 142)], width=10)
    line(d, [(116, 88), (116, 142)], width=10)
    return im


# ---------------------------------------------------------------------------
# 图像变换（工具栏第二行用）
# ---------------------------------------------------------------------------

def icon_adjust():
    """图像调节：三条滑块"""
    im = canvas(); d = ImageDraw.Draw(im)
    for y, kx in ((52, 138), (100, 74), (148, 118)):
        line(d, [(36, y), (164, y)], width=12, color=(26, 26, 26, 90))
        d.ellipse([kx - 17, y - 17, kx + 17, y + 17], fill=INK)
    return im


def icon_gray():
    """灰度化：画框 + 左黑右白圆"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, 170, 170], radius=12, outline=INK, width=14)
    d.pieslice([58, 58, 142, 142], start=90, end=270, fill=INK)
    d.ellipse([58, 58, 142, 142], outline=INK, width=12)
    return im


def icon_binary():
    """二值化：画框 + 左半实心方"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, 170, 170], radius=12, outline=INK, width=14)
    d.rectangle([56, 56, 100, 144], fill=INK)
    d.rectangle([100, 56, 144, 144], outline=INK, width=10)
    return im


def icon_invert():
    """反相：黑白对半圆"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.pieslice([40, 40, 160, 160], start=90, end=270, fill=INK)
    d.pieslice([40, 40, 160, 160], start=270, end=90, outline=INK, width=W)
    line(d, [(100, 40), (100, 160)], width=14)
    return im


def icon_emboss():
    """浮雕：内外双框（立体台阶）"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.rounded_rectangle([32, 32, 168, 168], radius=12, outline=INK, width=W)
    d.rounded_rectangle([62, 62, 138, 138], radius=8, outline=INK, width=14)
    line(d, [(62, 62), (138, 62)], width=22)
    return im


def icon_canny():
    """边缘检测：虚线框 + 四角实角"""
    im = canvas(); d = ImageDraw.Draw(im)
    # 四角括号
    for cx, cy, dx, dy in ((36, 36, 1, 1), (164, 36, -1, 1),
                           (36, 164, 1, -1), (164, 164, -1, -1)):
        line(d, [(cx, cy + dy * 44), (cx, cy), (cx + dx * 44, cy)], width=16)
    # 中间虚线点阵（示意边缘）
    for x in range(66, 140, 26):
        d.ellipse([x - 5, 95, x + 5, 105], fill=INK)
    for y in range(66, 140, 26):
        d.ellipse([95, y - 5, 105, y + 5], fill=INK)
    return im


def icon_blur():
    """模糊：水滴 + 扩散环"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([62, 62, 138, 138], fill=INK)
    d.ellipse([34, 34, 78, 78], outline=INK, width=12)
    d.ellipse([122, 122, 166, 166], outline=INK, width=12)
    return im


def icon_sharpen():
    """锐化：三角刃"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.polygon([(100, 30), (168, 158), (32, 158)], outline=INK, width=W)
    line(d, [(100, 74), (100, 138)], width=12)
    line(d, [(72, 138), (128, 138)], width=12)
    return im


def _rotate_arc(d, clockwise=True):
    """旋转图标：270° 圆弧 + 末端箭头。

    PIL 角度自 3 点钟方向顺时针增大（y 轴向下）。两条图标共用同一段
    45°→315° 的弧（缺口在右上），仅箭头位置与朝向不同：
    - 顺时针：箭头在弧末端（315°，右上）沿运动方向（向右下）；
    - 逆时针：箭头在弧首端（45°，右下）沿反向运动（向右上）。
    """
    d.arc([36, 36, 164, 164], start=45, end=315, fill=INK, width=W)
    r = 64.0
    theta = math.radians(315 if clockwise else 45)
    hx = 100 + r * math.cos(theta)
    hy = 100 + r * math.sin(theta)
    arrow_head(d, (hx, hy), math.degrees(theta) + (90 if clockwise else -90),
               size=48)


def icon_rotate_cw():
    """顺时针旋转"""
    im = canvas(); d = ImageDraw.Draw(im)
    _rotate_arc(d, clockwise=True)
    return im


def icon_rotate_ccw():
    """逆时针旋转"""
    im = canvas(); d = ImageDraw.Draw(im)
    _rotate_arc(d, clockwise=False)
    return im


def icon_flip_v():
    """垂直翻转：上下镜像三角"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.polygon([(100, 40), (150, 96), (50, 96)], fill=INK)
    d.polygon([(100, 160), (150, 104), (50, 104)], outline=INK, width=W)
    line(d, [(36, 100), (164, 100)], width=10, color=(26, 26, 26, 90))
    return im


def icon_flip_h():
    """水平翻转：左右镜像三角"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.polygon([(40, 100), (96, 50), (96, 150)], fill=INK)
    d.polygon([(160, 100), (104, 50), (104, 150)], outline=INK, width=W)
    line(d, [(100, 36), (100, 164)], width=10, color=(26, 26, 26, 90))
    return im


def icon_info():
    """图像信息：信息符号"""
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse([34, 34, 166, 166], outline=INK, width=W)
    d.ellipse([92, 62, 108, 78], fill=INK)
    line(d, [(100, 88), (100, 142)], width=18)
    return im


ICONS = {
    "arrow": icon_arrow,
    "annotArrow": icon_annot_arrow,
    "text": icon_text,
    "textNote": icon_text_note,
    "picker": icon_picker,
    "undo": icon_undo,
    "redo": icon_redo,
    "distance": icon_distance,
    "angle": icon_angle,
    "area": icon_area,
    "radius": icon_radius,
    "calibrate": icon_calibrate,
    "scalebar": icon_scalebar,
    "camera": icon_camera,
    "video": icon_video,
    "zoomIn": icon_zoom_in,
    "zoomOut": icon_zoom_out,
    "zoomFit": icon_zoom_fit,
    "zoomFill": icon_zoom_fill,
    "zoom100": icon_zoom_100,
    "locate": icon_locate,
    "trash": icon_trash,
    "adjust": icon_adjust,
    "gray": icon_gray,
    "binary": icon_binary,
    "invert": icon_invert,
    "emboss": icon_emboss,
    "canny": icon_canny,
    "blur": icon_blur,
    "sharpen": icon_sharpen,
    "rotateCW": icon_rotate_cw,
    "rotateCCW": icon_rotate_ccw,
    "flipV": icon_flip_v,
    "flipH": icon_flip_h,
    "info": icon_info,
}

def normalize_icon(path):
    """把单个 PNG 归一化：内容包围盒 -> 等比缩放至 TARGET -> 居中。

    两步缩放：先用 LANCZOS 保证形状质量，再紧致裁剪后用 NEAREST 精确钉到
    TARGET，消除 LANCZOS 抗锯齿羽化导致的 1~2px 包围盒误差，
    确保所有图标内容最大边严格一致（测试 ``len(set(sizes))==1``）。
    """
    im = Image.open(path).convert("RGBA")
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return False
    cropped = im.crop(bbox)
    cw, ch = cropped.size
    scale = TARGET / float(max(cw, ch))
    nw = max(1, int(round(cw * scale)))
    nh = max(1, int(round(ch * scale)))
    resized = cropped.resize((nw, nh), Image.LANCZOS)
    # 二次紧致裁剪：去掉 LANCZOS 在边缘产生的半透明羽化
    rbbox = resized.split()[3].getbbox()
    if rbbox:
        tight = resized.crop(rbbox)
        tw, th = tight.size
        s2 = TARGET / float(max(tw, th))
        nw2 = max(1, int(round(tw * s2)))
        nh2 = max(1, int(round(th * s2)))
        # 精确钉到 TARGET：NEAREST 无边沿羽化，包围盒即整数尺寸
        resized = tight.resize((nw2, nh2), Image.NEAREST)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(resized, ((SIZE - resized.width) // 2, (SIZE - resized.height) // 2), resized)
    out.save(path)
    return True


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in ICONS.items():
        im = fn()
        im.save(os.path.join(OUT, name + ".png"))
        print("generated", name + ".png")
    # 尺寸归一化：全部图标统一视觉大小
    n = 0
    for f in sorted(os.listdir(OUT)):
        if f.lower().endswith(".png"):
            if normalize_icon(os.path.join(OUT, f)):
                n += 1
    print("normalized %d icons to content box <= %dpx" % (n, TARGET))
