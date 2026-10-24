# PixelMark 架构与设计说明

本文面向开发者，说明模块划分、关键数据结构与设计决策。

---

## 1. 总体结构

```
pixelmark/
├── app.py            应用装配（QApplication、日志、异常钩子、资源初始化、高DPI）
├── main_window.py    主窗口：菜单/工具栏/状态栏/对话框编排（UI 控制器）
├── canvas.py         CanvasWidget：画布模型 + 视图(缩放) + 鼠标交互 + 历史栈
├── tools.py          工具枚举 ToolID 与元数据表 TOOLS
├── measurement.py    测量模型 Measurement、几何计算、Scale、渲染
├── capture.py        摄像头拍照 / 视频截帧（cv2 惰性导入，带降级提示）
├── dialogs.py        文字输入 / 比例尺标定 / 图像调节 / 帮助 / 关于
├── resources.py      资源加载（编译资源优先、磁盘回退）
├── util/
│   ├── imageutil.py  QImage ↔ numpy ↔ cv2 转换、调整、滤镜、泛洪填充
│   ├── logging.py    日志配置（滚动文件 + 控制台）
│   └── errors.py     异常类型、safe_call、全局 excepthook
└── view/             qtDesigner 界面（.ui）+ pyuic5 生成代码（*_ui.py）
```

**分层原则**：

- `canvas.py` 不知道菜单与对话框的存在，只通过信号对外通信；
- `main_window.py` 不知道绘图的实现细节，只调用 canvas 的公开方法；
- `measurement.py` 是纯数据 + 纯几何 + 自包含渲染，可独立测试；
- `util/imageutil.py` 是纯函数库（QImage 进、QImage 出），不依赖界面。

```
main_window ──信号──> CanvasWidget ──> Measurement(imageutil)
     │                    │
     └──> dialogs <───────┘
```

---

## 2. 关键设计

### 2.1 画布：图像 + 双缓冲预览 + 测量叠加层 + 缩放视图

`CanvasWidget` 持有三层内容：

| 层 | 字段 | 说明 |
|---|---|---|
| 提交层 | `self.image` | 已确认的图像内容（绘图/滤镜的结果） |
| 预览层 | `self.preview` | 拖拽中的形状（双缓冲，源自既有方案） |
| 叠加层 | `self.measurements` | 测量标注对象列表，绘制在提交层之上 |

#### 视图变换模型

- 显示尺寸 = 图像尺寸 × `zoom`；控件 `minimumSize` 驱动外层 `QScrollArea`
  的滚动条，控件被布局拉伸时由 `_image_rect()` 计算居中偏移（letterbox）；
- `map_to_image(pos)` 把所有鼠标坐标除以 zoom 换算回**图像坐标**，
  绘图与测量逻辑全部保持在图像坐标系，与当前缩放完全解耦；
- `auto_fit` 模式下，主窗口通过**视口事件过滤器**在窗口尺寸变化时
  调用 `refit_if_auto()` 重新计算缩放（导入、新建、还原后同样触发）；
- `Ctrl+滚轮` 缩放、中键拖拽平移（操作外层滚动条）；
- 缩放只改显示：测量值按像素计算，保存的图像分辨率不受影响。

`paintEvent` 顺序：背景 → `preview or image`（按缩放绘制）→ 全部测量 →
正在创建的测量预览；测量叠加层与图像共用同一 `translate+scale` 变换。
鼠标事件全部在控件内处理，坐标为控件本地坐标（早期实现需要
`mapToGlobal` + `mapFromGlobal` 换算，且事件挂在窗口上会越界错乱）。

### 2.2 统一历史栈（撤销/重做）

```python
self._history = []   # [(kind, payload)]  kind ∈ {'image', 'measure'}
self._future = []    # redo 栈
```

- 任何修改前调用 `begin_action(kind)`：压入当前状态快照、清空 redo；
- `undo()` 弹出最近动作、把当前状态压入 redo、恢复快照；
- 图像快照为 `QImage.copy()`，测量快照为列表浅拷贝；
- 上限 40 步 + 256MB 总预算（超出从最旧淘汰），保证大图也不会爆内存。

因为历史栈统一记录"动作类型"，绘图与测量的交错操作也能正确回退。

### 2.3 测量模型

```python
@dataclass
class Measurement:
    kind: str          # distance/angle/rect_area/circle/text/arrow/scalebar/calibrate
    points: list       # QPointF 几何点
    label: str         # 文字内容
    px_value: float    # 主数值（像素）
    ...
```

- `value_text(scale)` 生成人类可读结果（未标定显示 px，已标定附带实际值）；
- `csv_row(index, scale)` 生成导出行；
- `hit_test(point)` 命中测试（列表从上层往下找，支撑点选高亮）；
- `draw(painter, scale, selected, font)` 自包含渲染，异常被单点捕获不影响整体。

几何函数（`distance/angle_at/rect_area/circle_metrics/polygon_area`）为纯函数，
`Scale.from_lengths()` 负责比例换算与参数校验（非法抛 `ScaleError`）。

#### 比例尺与单位换算

```python
UNIT_TO_MM = {"μm":0.001, "mm":1.0, "cm":10.0, "m":1000.0, "in":25.4, ...}
Scale(pixels_per_unit=30.0, unit="mm")      # 30 px = 1 mm
scale.convert_to("cm")                      # -> 300 px/cm，标定关系不变
```

- `pixels_per_unit` 始终表示"每当前单位多少像素"，换算只改单位与系数；
- 像素（px）与长度单位不可互换算，`convert_to` 安全返回自身；
- 主窗口记录"标定基准单位"（`_base_unit`），显示单位下拉可在
  "跟随标定单位"与各预设之间切换，`_on_scale_changed` 同步下拉状态；
- 比例尺图形（scalebar）支持单击（整齐长度 `nice_scalebar_pixels`）
  与拖拽（自定义长度）两种创建方式，标签显示该图形的真实实际值。

### 2.4 图像处理：QImage ↔ numpy ↔ cv2

```
QImage --convertToFormat(RGBA8888)--> numpy (h,w,4) --[:, :, :3][..., ::-1]--> cv2 BGR
```

- **字节序**：所有转换统一先转 `Format_RGBA8888`，内存布局即 R,G,B,A，
  避免把 `Format_RGB32` 当作 RGBA 解释的隐患；
- **缓冲区读取**：`bits().asstring()`（先 `setsize`），兼容不同 PyQt5 小版本；
- **cv2 可选**：模块级惰性导入，失败则 numpy/Pillow 回退
  （高斯模糊用可分离卷积、Canny 用 Sobel、泛洪填充用扫描线算法）；
- **灰度输出**：`Format_Grayscale8`（早期 `Format_Indexed8` 无颜色表会显黑）。

#### 饱和度算法与 Qt 颜色链路的逐位一致

Qt 颜色链路 `QColor(rgb).toHsl() → S+v → setHsl() → getRgb()` 有两个 Qt 历史特性：

1. `toHsl().saturation()` 报告的是 **HSV 式饱和度** `d/max`（实测 5000/5000 一致）；
2. `setHsl()` 却按**标准 HSL** 解释饱和度，且往返不守恒（2000 例仅 3 例恒等）。

新版向量化复刻了完整量化链路（色相截断到整度、S/L 半进位取整、
灰度像素保持灰度、输出半进位远离零），因此数值一致：
亮度/暖色调逐点一致，对比度 ≤1，饱和度 ≤4（色相取整边界）。
相关结论来自对 Qt 5.15.9 的实测，见 `tests/test_imageutil.py`。

### 2.5 泛洪填充（油漆桶）

优先 `cv2.floodFill`（3 通道 + `FLOODFILL_FIXED_RANGE`，容差参数），
失败或 cv2 不可用时退回**扫描线填充**（行跨度栈 + numpy 逐span比较），
逐点 `drawPoint` 方案（大区域极慢）已被替换。
兼容函数 `floodFill(image, pos)` 保留原名返回点列表。

### 2.6 图像获取：摄像头与视频截帧（capture.py）

- `cv2` 惰性导入：`_import_cv2()` 失败时抛 `ImageLoadError`（含安装提示），
  由调用方转为友好对话框，不影响其余功能；
- `cv2_frame_to_qimage(frame)`：BGR → `QImage.Format_RGB888` 并 `.copy()`
  （脱离 numpy 缓冲区，避免悬垂引用）；
- `CameraCaptureDialog`：`enumerate_cameras()` 探测 0–4 号设备，
  `QTimer` 约 30fps 取帧预览，`closeEvent` 释放设备；
- `VideoFrameDialog`：进度滑块定位（`CAP_PROP_POS_FRAMES`）、
  播放/暂停/单帧步进、截取当前帧载入画布或另存图片；
- 两个对话框都通过 `captured(QImage)` 信号把结果交给主窗口，
  与画布的 `load_image()`（可撤销）衔接。

### 2.7 错误处理体系

| 层 | 机制 |
|---|---|
| 业务异常 | `PixelError` 体系（`ImageLoadError/ImageSaveError/ScaleError`） |
| 兜底执行 | `util.errors.safe_call`（记录日志，返回 (ok, result)） |
| 全局钩子 | `install_excepthook`：日志 + `QMessageBox`（含堆栈），程序不退出 |
| Qt 消息 | `qInstallMessageHandler` 把 Qt 警告/致命错误写入日志 |
| 日志 | `RotatingFileHandler` 2MB×5，`logs/` 不可写时回退临时目录 |
| 输入校验 | 笔刷大小范围化、颜色取消保护、空图像保护、比例尺参数校验 |

---

## 3. UI 构建链

```
pixelmark/view/*.ui  --pyuic5 (tools/build_ui.py)-->  *_ui.py
imgs.qrc            --pyrcc5---------------------->  img_resources.py
img/*.png           --tools/make_icons.py---------->  新增图标
```

- `build_ui.py` 会剥离 pyuic 自动附加的 `import imgs_rc`
  （资源由 `app.py` → `resources.py` 统一加载，并带磁盘回退）；
- `MainWindow.ui` 中将 `board` 提升为自定义控件 `CanvasWidget`
  （`<customwidgets>` 声明，header 为 `pixelmark.canvas`）；
- 早期控件对象名（`penBtn/bucketBtn/lineBtn/rectBtn/ellipseBtn/eraseButton/
  preColorBtn/backColorBtn/penSizeBtn/baseAdjustBtn/grayBtn/binaryBtn/invertBtn/
  embossBtn/cannyBtn/blurBtn/sharpenBtn` 及全部 action）**逐一保留**，
  便于老用户与后续维护对照。

---

## 4. 测试策略

```bash
python tools/run_tests.py
```

| 套件 | 内容 |
|---|---|
| `tests/test_measurement.py` | 几何、比例尺、单位换算、格式化、测量对象、命中测试、离屏绘制 |
| `tests/test_imageutil.py` | 转换往返、非正方形无花屏、各滤镜、泛洪填充、空图保护 |
| `tests/test_capture.py` | 单位系数表、Scale.convert_to、整齐长度选取、BGR→QImage 转换 |
| `tests/test_headless_ui.py` | 全流程 UI：17 工具点击、模拟鼠标绘制/测量、撤销重做、滤镜、旋转、保存/打开/导出、缩放坐标映射、单位切换、摄像头/视频降级、错误路径 |

无头运行使用 `QT_QPA_PLATFORM=offscreen`；
模态对话框在测试中以假对话框替换（`pixelmark.dialogs` /
`pixelmark.main_window` / `pixelmark.capture` 命名空间补丁），避免阻塞。
测试中的鼠标坐标一律为**图像坐标**，由 `_to_widget()` 按当前缩放与
居中偏移换算，因此与窗口大小、缩放比例解耦。
无头环境下 PyQt5 退出时存在已知段错误问题，测试运行器用 `os._exit` 规避
（与测试逻辑无关）。

---

## 5. 已知限制与后续方向

- 测量标注暂不支持拖动改位（可删除重建）；
- 摄像头预览为单线程 QTimer 取帧，极高分辨率下可改为 QThread；
- 油漆桶容差固定为 0（精确匹配）；
- 后续可考虑：多边形/折线测量、标定模板保存、PDF 导出、最近文件列表。
