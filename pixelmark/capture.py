# -*- coding: utf-8 -*-
"""图像获取：摄像头拍照 / 视频截帧。

两者都依赖 OpenCV（cv2）。cv2 不可用时对话框会给出友好提示，
不会导致程序崩溃；用户可选择安装 opencv-python 后重试。
"""

import os

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QSlider,
                             QVBoxLayout)

from . import __app_name__
from .util.errors import ImageLoadError
from .util.logging import get_logger

logger = get_logger("capture")

PREVIEW_INTERVAL_MS = 33          # 约 30fps 预览
MAX_CAMERA_INDEX = 4              # 枚举 0..4 号摄像头


def _import_cv2():
    """惰性导入 OpenCV；不可用时抛出 ImageLoadError（含安装提示）。"""
    try:
        import cv2  # noqa: WPS433 - 运行时按需导入
        return cv2
    except Exception as exc:  # noqa: BLE001
        raise ImageLoadError(
            "未检测到 OpenCV（cv2），摄像头与视频功能不可用。\n"
            "请安装：pip install opencv-python\n（%s）" % exc)


def cv2_frame_to_qimage(frame):
    """OpenCV BGR 帧 -> QImage（RGB 副本，数据独立安全）。"""
    if frame is None:
        raise ImageLoadError("视频帧为空")
    cv2 = _import_cv2()
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    except Exception as exc:  # noqa: BLE001
        raise ImageLoadError("无法转换视频帧色彩空间: %s" % exc)
    h, w = rgb.shape[:2]
    ch = rgb.shape[2] if rgb.ndim == 3 else 1
    if ch == 3:
        fmt = QImage.Format_RGB888
    else:
        raise ImageLoadError("不支持的帧格式: %s" % rgb.shape)
    image = QImage(rgb.data, w, h, ch * w, fmt)
    return image.copy()


def enumerate_cameras():
    """枚举可用摄像头，返回 [(index, name)]；无摄像头时返回空列表。"""
    cv2 = _import_cv2()
    found = []
    for idx in range(MAX_CAMERA_INDEX + 1):
        try:
            cap = cv2.VideoCapture(idx)
            if cap is not None and cap.isOpened():
                ok, _frame = cap.read()
                if ok:
                    found.append((idx, "摄像头 %d" % idx))
            if cap is not None:
                cap.release()
        except Exception as exc:  # noqa: BLE001
            logger.warning("枚举摄像头 %d 失败: %s", idx, exc)
    return found


# ---------------------------------------------------------------------------
# 摄像头拍照
# ---------------------------------------------------------------------------

class CameraCaptureDialog(QDialog):
    """摄像头实时预览并拍照，照片直接载入画布。"""

    captured = pyqtSignal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("摄像头拍照")
        self.resize(760, 620)
        self.cap = None
        self.current_frame = None
        self._building = True

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("设备："))
        self.deviceCombo = QComboBox()
        row.addWidget(self.deviceCombo)
        row.addStretch(1)
        self.statusLabel = QLabel("正在初始化…")
        row.addWidget(self.statusLabel)
        layout.addLayout(row)

        self.previewLabel = QLabel("摄像头预览")
        self.previewLabel.setAlignment(Qt.AlignCenter)
        self.previewLabel.setMinimumSize(480, 360)
        self.previewLabel.setStyleSheet(
            "background:#2E3238; color:#C8CCD2; border-radius:6px;")
        layout.addWidget(self.previewLabel, 1)

        buttons = QHBoxLayout()
        self.shootBtn = QPushButton("拍照并载入画布")
        self.shootBtn.setMinimumHeight(32)
        self.shootBtn.setEnabled(False)
        self.shootBtn.clicked.connect(self._shoot)
        cancelBtn = QPushButton("取消")
        cancelBtn.clicked.connect(self.reject)
        buttons.addWidget(self.shootBtn, 1)
        buttons.addWidget(cancelBtn)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._grab)

        self._building = False
        self._init_devices()

    # ---- 设备 ----
    def _init_devices(self):
        try:
            cams = enumerate_cameras()
        except ImageLoadError as exc:
            self.statusLabel.setText(str(exc).splitlines()[0])
            QMessageBox.warning(self, "摄像头不可用", str(exc))
            return
        if not cams:
            self.statusLabel.setText("未检测到可用摄像头")
            QMessageBox.information(self, "摄像头拍照",
                                    "未检测到可用摄像头。\n请连接摄像头后重试。")
            return
        for idx, name in cams:
            self.deviceCombo.addItem(name, idx)
        self.deviceCombo.currentIndexChanged.connect(self._switch_device)
        self._switch_device()

    def _switch_device(self):
        self._stop()
        idx = self.deviceCombo.currentData()
        if idx is None:
            return
        try:
            cv2 = _import_cv2()
            self.cap = cv2.VideoCapture(idx)
            if self.cap is None or not self.cap.isOpened():
                raise ImageLoadError("无法打开摄像头 %s" % idx)
        except ImageLoadError as exc:
            self.cap = None
            self.statusLabel.setText(str(exc).splitlines()[0])
            QMessageBox.warning(self, "摄像头打开失败", str(exc))
            return
        self.statusLabel.setText("预览中…（%dx%d）" % (
            int(self.cap.get(3)), int(self.cap.get(4))))
        self.shootBtn.setEnabled(True)
        self.timer.start(PREVIEW_INTERVAL_MS)

    def _stop(self):
        self.timer.stop()
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as exc:  # noqa: BLE001
                logger.warning("释放摄像头失败: %s", exc)
            self.cap = None

    # ---- 预览与拍照 ----
    def _grab(self):
        if self.cap is None:
            return
        try:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                self.statusLabel.setText("读取摄像头画面失败")
                return
            image = cv2_frame_to_qimage(frame)
            self.current_frame = image
            pix = QPixmap.fromImage(image)
            self.previewLabel.setPixmap(pix.scaled(
                self.previewLabel.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except ImageLoadError as exc:
            logger.warning("摄像头取帧失败: %s", exc)
            self.statusLabel.setText("取帧失败: %s" % str(exc).splitlines()[0])

    def _shoot(self):
        if self.current_frame is None:
            QMessageBox.information(self, "拍照", "尚未获取到画面，请稍候重试。")
            return
        self.captured.emit(self.current_frame)
        self.accept()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# 视频截帧
# ---------------------------------------------------------------------------

class VideoFrameDialog(QDialog):
    """打开视频文件，逐帧预览并截取当前帧。"""

    captured = pyqtSignal(QImage)

    def __init__(self, parent=None, video_path=None):
        super().__init__(parent)
        self.setWindowTitle("从视频获取照片")
        self.resize(820, 680)
        self.cap = None
        self.current_frame = None
        self.total_frames = 0
        self.fps = 25.0
        self.playing = False

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.pathEdit = QLabel("未选择视频")
        self.pathEdit.setStyleSheet("color:#555;")
        row.addWidget(self.pathEdit, 1)
        openBtn = QPushButton("打开视频…")
        openBtn.clicked.connect(self._choose_file)
        row.addWidget(openBtn)
        layout.addLayout(row)

        self.previewLabel = QLabel("视频预览")
        self.previewLabel.setAlignment(Qt.AlignCenter)
        self.previewLabel.setMinimumSize(520, 380)
        self.previewLabel.setStyleSheet(
            "background:#2E3238; color:#C8CCD2; border-radius:6px;")
        layout.addWidget(self.previewLabel, 1)

        # 进度条
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(self._pause_for_seek)
        self.slider.sliderReleased.connect(self._seek_released)
        layout.addWidget(self.slider)

        self.infoLabel = QLabel("帧 0 / 0 · 00:00.00")
        self.infoLabel.setStyleSheet("color:#555;")
        layout.addWidget(self.infoLabel)

        # 控制按钮
        ctrl = QHBoxLayout()
        self.playBtn = QPushButton("播放")
        self.playBtn.setEnabled(False)
        self.playBtn.clicked.connect(self._toggle_play)
        prevBtn = QPushButton("◀ 上一帧")
        prevBtn.clicked.connect(lambda: self._step(-1))
        nextBtn = QPushButton("下一帧 ▶")
        nextBtn.clicked.connect(lambda: self._step(1))
        saveBtn = QPushButton("保存当前帧为图片…")
        saveBtn.clicked.connect(self._save_frame)
        self.shootBtn = QPushButton("截取当前帧并载入画布")
        self.shootBtn.setMinimumHeight(32)
        self.shootBtn.setEnabled(False)
        self.shootBtn.clicked.connect(self._shoot)
        cancelBtn = QPushButton("取消")
        cancelBtn.clicked.connect(self.reject)
        ctrl.addWidget(self.playBtn)
        ctrl.addWidget(prevBtn)
        ctrl.addWidget(nextBtn)
        ctrl.addWidget(saveBtn)
        ctrl.addStretch(1)
        ctrl.addWidget(self.shootBtn, 1)
        ctrl.addWidget(cancelBtn)
        layout.addLayout(ctrl)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

        if video_path:
            self._open(video_path)

    # ---- 文件 ----
    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm);;所有文件 (*)")
        if path:
            self._open(path)

    def _open(self, path):
        self._pause()
        self._release()
        try:
            cv2 = _import_cv2()
            self.cap = cv2.VideoCapture(path)
            if self.cap is None or not self.cap.isOpened():
                raise ImageLoadError("无法打开视频文件（格式不支持或文件损坏）")
        except ImageLoadError as exc:
            self.cap = None
            self.pathEdit.setText("打开失败")
            QMessageBox.critical(self, "打开视频失败", "%s\n\n%s" % (path, exc))
            return
        self.pathEdit.setText(os.path.basename(path))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if self.fps <= 0:
            self.fps = 25.0
        self._pos_frames_prop = getattr(cv2, "CAP_PROP_POS_FRAMES", 1)
        self.slider.setEnabled(True)
        self.slider.setMaximum(max(0, self.total_frames - 1))
        self.slider.setValue(0)
        self.playBtn.setEnabled(True)
        self._show_frame(0)

    def _release(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as exc:  # noqa: BLE001
                logger.warning("释放视频失败: %s", exc)
            self.cap = None

    # ---- 帧显示 ----
    def _read_at(self, index):
        """定位到指定帧并读取，返回 (frame_no, frame)。"""
        if self.cap is None:
            return None, None
        index = max(0, min(index, max(0, self.total_frames - 1)))
        try:
            self.cap.set(getattr(self, "_pos_frames_prop", 1), index)
            ok, frame = self.cap.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取视频帧失败: %s", exc)
            return None, None
        if not ok or frame is None:
            return None, None
        return index, frame

    def _show_frame(self, index):
        idx, frame = self._read_at(index)
        if frame is None:
            self.infoLabel.setText("无法读取该帧")
            return
        try:
            image = cv2_frame_to_qimage(frame)
        except ImageLoadError as exc:
            self.infoLabel.setText("帧转换失败: %s" % str(exc).splitlines()[0])
            return
        self.current_frame = image
        self.previewLabel.setPixmap(QPixmap.fromImage(image).scaled(
            self.previewLabel.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._frame_no = idx
        self.slider.blockSignals(True)
        self.slider.setValue(idx)
        self.slider.blockSignals(False)
        secs = idx / self.fps if self.fps else 0.0
        self.infoLabel.setText("帧 %d / %d · %05.2f 秒" % (idx, self.total_frames, secs))

    # ---- 播放 ----
    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        if self.cap is None:
            return
        self.playing = True
        self.playBtn.setText("暂停")
        self.timer.start(int(1000 / self.fps))

    def _pause(self):
        self.playing = False
        self.playBtn.setText("播放")
        self.timer.stop()

    def _pause_for_seek(self):
        self._was_playing = self.playing
        self._pause()

    def _seek_released(self):
        self._show_frame(self.slider.value())
        if getattr(self, "_was_playing", False):
            self._play()

    def _advance(self):
        if self.cap is None:
            return
        idx = getattr(self, "_frame_no", 0) + 1
        if self.total_frames and idx >= self.total_frames:
            self._pause()
            return
        try:
            ok, frame = self.cap.read()
        except Exception:  # noqa: BLE001
            self._pause()
            return
        if not ok or frame is None:
            self._pause()
            return
        try:
            image = cv2_frame_to_qimage(frame)
        except ImageLoadError:
            self._pause()
            return
        self.current_frame = image
        self.previewLabel.setPixmap(QPixmap.fromImage(image).scaled(
            self.previewLabel.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._frame_no = idx
        self.slider.blockSignals(True)
        self.slider.setValue(idx)
        self.slider.blockSignals(False)
        secs = idx / self.fps if self.fps else 0.0
        self.infoLabel.setText("帧 %d / %d · %05.2f 秒" % (idx, self.total_frames, secs))

    def _step(self, delta):
        self._pause()
        self._show_frame(getattr(self, "_frame_no", 0) + delta)

    # ---- 截取 / 保存 ----
    def _shoot(self):
        if self.current_frame is None:
            QMessageBox.information(self, "截取帧", "尚未加载视频帧。")
            return
        self.captured.emit(self.current_frame)
        self.accept()

    def _save_frame(self):
        if self.current_frame is None:
            QMessageBox.information(self, "保存帧", "尚未加载视频帧。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存当前帧", "frame_%d.png" % getattr(self, "_frame_no", 0),
            "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)")
        if not path:
            return
        if not self.current_frame.save(path):
            QMessageBox.critical(self, "保存失败", "无法写入文件：\n%s" % path)
            return
        self.infoLabel.setText("已保存 %s" % path)

    def closeEvent(self, event):
        self._pause()
        self._release()
        super().closeEvent(event)
