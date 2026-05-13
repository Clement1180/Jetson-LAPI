import cv2
import logging
import time
from typing import Optional, Tuple

log = logging.getLogger("lapi.camera")


def build_gstreamer_pipeline(width: int = 1920, height: int = 1080, fps: int = 30,
                              sensor_id: int = 0, flip: int = 0) -> str:
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"format=NV12, framerate={fps}/1 ! "
        f"nvvidconv flip-method={flip} ! "
        f"video/x-raw, width={width}, height={height}, format=BGRx ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink drop=1"
    )


def build_v4l2_pipeline(device: str = "/dev/video0", width: int = 1920,
                         height: int = 1080, fps: int = 30) -> str:
    return (
        f"v4l2src device={device} ! "
        f"video/x-raw, width={width}, height={height}, framerate={fps}/1 ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink drop=1"
    )


class Camera:
    def __init__(self, source: str = "csi", width: int = 1920, height: int = 1080,
                 fps: int = 30, device: str = "/dev/video0", sensor_id: int = 0):
        self._source = source
        self._width = width
        self._height = height
        self._fps = fps
        self._device = device
        self._sensor_id = sensor_id
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        if self._source == "csi":
            pipeline = build_gstreamer_pipeline(self._width, self._height, self._fps,
                                                 self._sensor_id)
            log.info(f"Ouverture CSI: {pipeline}")
            self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        elif self._source == "v4l2":
            pipeline = build_v4l2_pipeline(self._device, self._width, self._height, self._fps)
            log.info(f"Ouverture V4L2: {pipeline}")
            self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        elif self._source == "usb":
            log.info(f"Ouverture USB: {self._device}")
            self._cap = cv2.VideoCapture(self._device)
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
                self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        else:
            # Fichier vidéo (pour tests)
            log.info(f"Ouverture fichier: {self._source}")
            self._cap = cv2.VideoCapture(self._source)

        if not self._cap or not self._cap.isOpened():
            log.error("Impossible d'ouvrir la caméra")
            return False

        log.info(f"Caméra ouverte: {self._width}x{self._height}@{self._fps}fps")
        return True

    def read(self) -> Optional[any]:
        if not self._cap or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        return frame

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None
            log.info("Caméra libérée")

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
