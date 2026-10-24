# -*- coding: utf-8 -*-
"""图像处理工具集（PyQt5 QImage <-> numpy <-> OpenCV）。

主要特性：
1. **修复坐标寻址**：``adjustBright/adjustWarm/adjustSaturation/adjustContrast``
   严格按 (列=x, 行=y) 寻址，非正方形图像不再出现整条带花屏。
2. **性能**：全部采用 numpy 向量化运算，800x600 图像处理为毫秒级，
   调节滑块可实时预览。
3. **健壮性**：OpenCV 惰性导入且可选——缺失或与 Qt 冲突时自动退回到
   numpy/Pillow 实现；所有函数对空图像/异常格式做了保护。
4. 提供完整的亮度/暖色/饱和度/对比度/灰度/二值化/反相/浮雕/
   边缘检测/模糊/锐化/泛洪填充能力，行为稳定可预期。
"""

import numpy as np
from PyQt5.QtGui import QImage

from .logging import get_logger
from .errors import ImageLoadError

logger = get_logger("imageutil")

# ---------------------------------------------------------------------------
# OpenCV 惰性导入（可选依赖）
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 取决于运行环境
    import cv2 as _cv2
    _HAS_CV2 = True
except Exception as _exc:  # noqa: BLE001 - cv2 缺失或与 Qt 冲突时静默降级
    _cv2 = None
    _HAS_CV2 = False
    logger.warning("OpenCV 不可用（%s），相关滤镜将使用 numpy/Pillow 回退实现", _exc)


def bound(low, high, value):
    """把 value 限制在 [low, high]。"""
    return low if value < low else high if value > high else value


# ---------------------------------------------------------------------------
# QImage <-> numpy
# ---------------------------------------------------------------------------

def _img_buffer_bytes(image):
    """安全取出 QImage 的像素字节（兼容不同 PyQt5 小版本）。

    优先 ``bits().asstring()``（PyQt5 经典用法，需先 setsize）；
    失败时尝试 ``constBits().asstring()``。
    """
    need = image.byteCount()
    for getter in (image.bits, image.constBits):
        try:
            ptr = getter()
            ptr.setsize(need)
            return ptr.asstring()
        except Exception:  # noqa: BLE001 - 尝试下一种方式
            continue
    raise ImageLoadError("无法读取图像像素数据（PyQt5 版本不兼容）")


def qimage_to_np(image):
    """QImage -> numpy RGBA 数组 (height, width, 4)，总是返回副本。"""
    if image is None or image.isNull():
        raise ImageLoadError("图像为空")
    img = image
    if img.format() != QImage.Format_RGBA8888:
        img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        raise ImageLoadError("图像尺寸非法: %dx%d" % (w, h))
    arr = np.frombuffer(_img_buffer_bytes(img), dtype=np.uint8)
    need = h * w * 4
    if arr.size < need:
        raise ImageLoadError("像素数据不完整: %d < %d" % (arr.size, need))
    return arr[:need].reshape((h, w, 4)).copy()


def np_to_qimage(arr):
    """numpy 数组 (h, w, 3|4) -> QImage(Format_RGBA8888)，返回独立副本。"""
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    if arr.ndim != 3 or arr.shape[2] not in (3, 4):
        raise ImageLoadError("不支持的数组形状: %s" % (arr.shape,))
    h, w = arr.shape[:2]
    if w <= 0 or h <= 0:
        raise ImageLoadError("图像尺寸非法: %dx%d" % (w, h))
    if arr.shape[2] == 3:
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        arr = np.concatenate([arr, alpha], axis=2)
    image = QImage(arr.tobytes(), w, h, 4 * w, QImage.Format_RGBA8888)
    return image.copy()  # 脱离 numpy 缓冲区


def _luminance(rgba):
    """RGBA -> 灰度（Rec.601 权重，与 OpenCV RGB2GRAY 一致）。"""
    return (rgba[..., 0].astype(np.float32) * 0.299 +
            rgba[..., 1].astype(np.float32) * 0.587 +
            rgba[..., 2].astype(np.float32) * 0.114).round().astype(np.uint8)


# ---------------------------------------------------------------------------
# 颜色调整（修复原坐标 bug + 向量化）
# ---------------------------------------------------------------------------

def _prepare(image):
    rgba = qimage_to_np(image)
    return rgba


def _finish(rgba):
    return np_to_qimage(rgba)


def adjustBright(image, value):
    """调整亮度：RGB 同时加减 value（-255..255）。"""
    rgba = _prepare(image)
    v = int(bound(-255, 255, value))
    if v == 0:
        return _finish(rgba)
    rgba[..., :3] = np.clip(rgba[..., :3].astype(np.int16) + v, 0, 255).astype(np.uint8)
    return _finish(rgba)


def adjustWarm(image, value):
    """调整暖色调：value>=0 加红绿，value<0 加蓝。"""
    rgba = _prepare(image)
    v = int(bound(-255, 255, value))
    if v == 0:
        return _finish(rgba)
    rgb = rgba[..., :3].astype(np.int16)
    if v >= 0:
        rgb[..., 0] = np.clip(rgb[..., 0] + v, 0, 255)
        rgb[..., 1] = np.clip(rgb[..., 1] + v, 0, 255)
    else:
        rgb[..., 2] = np.clip(rgb[..., 2] - v, 0, 255)
    rgba[..., :3] = rgb.astype(np.uint8)
    return _finish(rgba)


def adjustSaturation(image, value):
    """调整饱和度：Qt HSL 饱和度(0..255)加减 value。

    数值与 Qt 颜色链路一致（含 Qt 的两个历史特性）：
    - ``QColor.toHsl().saturation()`` 报告的是 HSV 式饱和度 d/max；
    - ``QColor.setHsl()`` 却按标准 HSL 解释饱和度；
    - 色相取整为度（截断），灰度像素保持灰度。
    本函数逐量化复刻该链路，因此数值逐点一致（舍入差 ≤1）。
    """
    rgba = _prepare(image)
    v = int(bound(-255, 255, value))
    if v == 0:
        return _finish(rgba)
    rgb = rgba[..., :3].astype(np.float64)
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    d = mx - mn

    # --- 复刻 QColor.toHsl() 的整数量化 ---
    hue = _hue_of(rgb, mx, mn, d) * 360.0          # 0..360 浮点
    H = np.floor(hue)                              # Qt 截断到整度
    S = np.where(mx > 0, np.floor(d / np.maximum(mx, 1e-6) * 255.0 + 0.5), 0.0)  # HSV 式 S
    L = np.floor((mx + mn) * 0.5 + 0.5)            # 0..255

    new_s = np.clip(S + v, 0, 255)
    # --- 复刻 QColor.setHsl() 的标准 HSL -> RGB（半进位远离零） ---
    out = _hsl_to_rgb(H / 360.0, new_s / 255.0, L / 255.0) * 255.0
    out = np.floor(out + 0.5).astype(np.uint8)
    # 灰度像素保持灰度
    achromatic = (d <= 0)
    if achromatic.any():
        gray = L.astype(np.uint8)
        out[achromatic] = np.stack([gray, gray, gray], axis=-1)[achromatic]
    rgba[..., :3] = out
    return _finish(rgba)


def _hue_of(rgb, mx, mn, d):
    """标准色相公式，返回 [0,1)。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    safe = np.maximum(d, 1e-6)
    idx = (mx == r) & (d > 0)
    h[idx] = ((g - b)[idx] / safe[idx]) % 6.0
    idx = (mx == g) & (d > 0)
    h[idx] = (b - r)[idx] / safe[idx] + 2.0
    idx = (mx == b) & (d > 0)
    h[idx] = (r - g)[idx] / safe[idx] + 4.0
    return (h / 6.0) % 1.0


def adjustContrast(image, value):
    """调整对比度：c' = c + (c - 127) * k。"""
    rgba = _prepare(image)
    v = float(bound(-99, 99, value))
    if v == 0:
        return _finish(rgba)
    k = (1.0 / (1.0 - v / 100.0) - 1.0) if v >= 0 else (v / 100.0)
    rgb = rgba[..., :3].astype(np.float32)
    out = np.clip((rgb - 127.0) * k + rgb + 0.5, 0, 255).astype(np.uint8)
    rgba[..., :3] = out
    return _finish(rgba)


# --- 向量化 HSL（与 Qt QColor 转换保持一致的舍入） -------------------------

def _rgb_to_hsl(rgb):
    """rgb: (..., 3) float 0..1 -> (h[0..1), s, l)。h 对灰度像素为 0。"""
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    l = (mx + mn) * 0.5
    d = mx - mn
    s = np.where(l > 0.5, d / np.maximum(2.0 - mx - mn, 1e-9),
                 d / np.maximum(mx + mn, 1e-9))
    s = np.where(d <= 0, 0.0, s)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    nz = d > 0
    idx = nz & (mx == r)
    h[idx] = ((g - b)[idx] / d[idx]) % 6.0
    idx = nz & (mx == g)
    h[idx] = (b - r)[idx] / d[idx] + 2.0
    idx = nz & (mx == b)
    h[idx] = (r - g)[idx] / d[idx] + 4.0
    h = (h / 6.0) % 1.0
    return h, np.clip(s, 0.0, 1.0), l


def _hue_to_rgb(p, q, t):
    t = t % 1.0
    out = np.zeros_like(t)
    out = np.where(t < 1 / 6, p + (q - p) * 6.0 * t, out)
    out = np.where((t >= 1 / 6) & (t < 1 / 2), q, out)
    out = np.where((t >= 1 / 2) & (t < 2 / 3), p + (q - p) * (2 / 3 - t) * 6.0, out)
    return np.where(t >= 2 / 3, p, out)


def _hsl_to_rgb(h, s, l):
    """h,s,l: (...,) float 0..1 -> rgb (..., 3)。"""
    q = np.where(l < 0.5, l * (1.0 + s), l + s - l * s)
    p = 2.0 * l - q
    r = _hue_to_rgb(p, q, h + 1 / 3)
    g = _hue_to_rgb(p, q, h)
    b = _hue_to_rgb(p, q, h - 1 / 3)
    return np.stack([r, g, b], axis=-1)


# ---------------------------------------------------------------------------
# 泛洪填充（油漆桶）
# ---------------------------------------------------------------------------

def getPixel(x, y, pixels, w):
    """按 RGBA 扁平缓冲取像素的兼容性接口。"""
    i = (x + (y * w)) * 4
    return pixels[i:i + 3]


def flood_fill_mask(image, pos, tolerance=0):
    """返回布尔掩码 (h, w)：与 ``pos`` 处颜色连通（容差 tolerance）的区域。

    pos 越界时返回 None。优先使用 OpenCV；不可用时退回扫描线算法。
    """
    rgba = qimage_to_np(image)
    h, w = rgba.shape[:2]
    x, y = int(round(pos.x())), int(round(pos.y()))
    if not (0 <= x < w and 0 <= y < h):
        return None
    tol = int(bound(0, 255, tolerance))

    if _HAS_CV2:
        try:
            mask = np.zeros((h + 2, w + 2), np.uint8)
            flags = 4 | (0x10000 if tol else 0)  # 4 连通 | FLOODFILL_FIXED_RANGE
            # cv2.floodFill 仅支持 1/3 通道；通道顺序不影响连通判定
            _cv2.floodFill(rgba[..., :3].copy(), mask, (x, y), (0, 0, 0),
                           loDiff=(tol,) * 3, upDiff=(tol,) * 3, flags=flags)
            return mask[1:-1, 1:-1].astype(bool)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cv2 泛洪填充失败，退回扫描线算法: %s", exc)
    return _scanline_fill(rgba, x, y, tol)


def _scanline_fill(rgba, x, y, tol):
    """扫描线泛洪填充（numpy + 行跨度，纯 Python 回退实现）。"""
    h, w = rgba.shape[:2]
    target = rgba[y, x].astype(np.int16)
    mask = np.zeros((h, w), dtype=bool)
    stack = [(x, y)]
    while stack:
        sx, sy = stack.pop()
        if mask[sy, sx]:
            continue  # 该种子所在行段已填充，避免相邻行互相重复推送形成死循环
        while sx >= 0 and _match(rgba[sy, sx], target, tol):
            sx -= 1
        sx += 1
        span_up = span_down = False
        while sx < w and _match(rgba[sy, sx], target, tol):
            mask[sy, sx] = True
            if sy > 0:
                up = _match(rgba[sy - 1, sx], target, tol)
                if up and not span_up:
                    stack.append((sx, sy - 1))
                    span_up = True
                elif not up:
                    span_up = False
            if sy < h - 1:
                down = _match(rgba[sy + 1, sx], target, tol)
                if down and not span_down:
                    stack.append((sx, sy + 1))
                    span_down = True
                elif not down:
                    span_down = False
            sx += 1
    return mask


def _match(pixel, target, tol):
    return bool(np.all(np.abs(pixel.astype(np.int16) - target) <= tol))


def floodFill(image, pos, color=None, tolerance=0):
    """兼容性接口：返回被填充的 (x, y) 位置列表。

    新代码请使用 :func:`flood_fill_mask`（性能更好）。颜色参数仅为兼容保留。
    """
    mask = flood_fill_mask(image, pos, tolerance)
    if mask is None:
        return []
    ys, xs = np.nonzero(mask)
    return list(zip(xs.tolist(), ys.tolist()))


def flood_fill(image, pos, color, opacity=1.0, tolerance=0):
    """把 pos 处连通区域填充为 color（QColor），返回新 QImage。"""
    mask = flood_fill_mask(image, pos, tolerance)
    if mask is None or not mask.any():
        return image
    rgba = qimage_to_np(image)
    fill = np.array([color.red(), color.green(), color.blue(), color.alpha()],
                    dtype=np.float32)
    alpha = float(bound(0.0, 1.0, opacity)) * (fill[3] / 255.0)
    old = rgba[..., :].astype(np.float32)
    blended = old * (1 - alpha) + fill * alpha
    rgba[mask] = np.clip(blended[mask].round(), 0, 255).astype(np.uint8)
    return np_to_qimage(rgba)


# ---------------------------------------------------------------------------
# OpenCV / numpy 滤镜
# ---------------------------------------------------------------------------

def QImageToCvMat(incomingImage):
    """QImage -> OpenCV Mat（BGRA，numpy 视图副本）。"""
    rgba = qimage_to_np(incomingImage)
    return rgba[..., :3][..., ::-1].copy()  # RGBA -> BGRA(3ch)


def CvMatToQImage(cvMat):
    """OpenCV Mat -> QImage。支持单通道与 3/4 通道。"""
    arr = np.asarray(cvMat)
    if arr.ndim == 2:
        gray = arr.astype(np.uint8)
        h, w = gray.shape
        image = QImage(gray.tobytes(), w, h, w, QImage.Format_Grayscale8)
        return image.copy()
    if arr.shape[2] == 4:
        rgba = arr[..., :3][..., ::-1]
        alpha = arr[..., 3:4]
        return np_to_qimage(np.concatenate([rgba, alpha], axis=-1))
    if arr.shape[2] == 3:
        return np_to_qimage(arr[..., ::-1])  # BGR -> RGB
    raise ImageLoadError("不支持的通道数: %s" % (arr.shape,))


def _convolve3x3(rgb, kernel):
    """3x3 卷积（边缘复制 padding），rgb 为 float32 (h, w, 3)。"""
    k = np.asarray(kernel, dtype=np.float32)
    padded = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    out = np.zeros_like(rgb)
    for dy in range(3):
        for dx in range(3):
            out += padded[dy:dy + rgb.shape[0], dx:dx + rgb.shape[1], :] * k[dy, dx]
    return out


def blur(image):
    """高斯模糊（sigma=15）。"""
    rgba = _prepare(image)
    rgb = rgba[..., :3]
    if _HAS_CV2:
        try:
            bgr = rgb[..., ::-1]
            dst = _cv2.GaussianBlur(bgr, (0, 0), sigmaX=15)
            rgba[..., :3] = dst[..., ::-1]
            return _finish(rgba)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cv2 模糊失败，使用 numpy 回退: %s", exc)
    rgba[..., :3] = _gaussian_blur_np(rgb, sigma=15)
    return _finish(rgba)


def _gaussian_blur_np(rgb, sigma):
    """可分离高斯卷积（numpy 回退实现）。"""
    radius = max(1, int(sigma * 3))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x ** 2) / (2 * sigma * sigma))
    k /= k.sum()
    out = rgb.astype(np.float32)
    padded = np.pad(out, ((0, 0), (radius, radius), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 1, padded)
    padded = np.pad(out, ((radius, radius), (0, 0), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 0, padded)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def sharpen(image):
    """锐化（3x3 核）。"""
    rgba = _prepare(image)
    kernel = [[0, -1, 0], [-1, 5, -1], [0, -1, 0]]
    rgb = rgba[..., :3].astype(np.float32)
    out = _convolve3x3(rgb, kernel)
    rgba[..., :3] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    return _finish(rgba)


def emboss(image):
    """浮雕（3x3 核）。"""
    rgba = _prepare(image)
    kernel = [[-2, -1, 0], [-1, 1, 1], [0, 1, 2]]
    rgb = rgba[..., :3].astype(np.float32)
    out = _convolve3x3(rgb, kernel)
    rgba[..., :3] = np.clip(out + 128 + 0.5, 0, 255).astype(np.uint8)
    return _finish(rgba)


def canny(image, t1=50, t2=150):
    """Canny 边缘检测（阈值 50/150）。"""
    rgba = _prepare(image)
    gray = _luminance(rgba)
    if _HAS_CV2:
        try:
            edges = _cv2.Canny(_cv2.GaussianBlur(gray, (3, 3), 0), t1, t2)
            gray = edges
        except Exception as exc:  # noqa: BLE001
            logger.warning("cv2 Canny 失败，使用 Sobel 回退: %s", exc)
            gray = _sobel_edges(gray)
    else:
        gray = _sobel_edges(gray)
    h, w = gray.shape
    out = QImage(gray.tobytes(), w, h, w, QImage.Format_Grayscale8)
    return out.copy()


def _sobel_edges(gray):
    """Sobel 梯度幅值（Canny 回退实现）。"""
    g = gray.astype(np.float32)
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = kx.T
    gx = _convolve3x3(g[..., None], kx)[..., 0]
    gy = _convolve3x3(g[..., None], ky)[..., 0]
    mag = np.hypot(gx, gy)
    return np.clip(mag + 0.5, 0, 255).astype(np.uint8)


def gray(image):
    """灰度化（输出 Format_Grayscale8，可正常显示）。"""
    rgba = _prepare(image)
    gray_arr = _luminance(rgba)
    h, w = gray_arr.shape
    out = QImage(gray_arr.tobytes(), w, h, w, QImage.Format_Grayscale8)
    return out.copy()


def binaryzation(image, threshold=127):
    """二值化（阈值 127）。"""
    rgba = _prepare(image)
    gray_arr = _luminance(rgba)
    binary = np.where(gray_arr > threshold, 255, 0).astype(np.uint8)
    h, w = binary.shape
    out = QImage(binary.tobytes(), w, h, w, QImage.Format_Grayscale8)
    return out.copy()


def invert(image):
    """反相（保留 Alpha 通道，向量化实现）。"""
    rgba = _prepare(image)
    if rgba.shape[2] == 4:
        rgba[..., :3] = 255 - rgba[..., :3]
    else:
        rgba = 255 - rgba
    return _finish(rgba)
