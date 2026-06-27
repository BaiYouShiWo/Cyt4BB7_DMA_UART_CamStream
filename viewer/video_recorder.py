"""Background video recorder."""

from __future__ import annotations

import threading
import time
from queue import Empty, Queue
from typing import Final

import cv2
import numpy as np

from config import (
    DEFAULT_RECORD_FPS,
    DEFAULT_VIDEO_EXTENSION,
    VIDEO_FOURCC_AVI,
    VIDEO_FOURCC_MP4,
    VIDEO_DIR,
)
from utils import next_filename


class VideoRecorder:
    """Record grayscale camera frames to a video file.

    The recorder is intentionally not a thread itself; it runs a worker thread
    that consumes frames from ``record_queue``. This keeps serial reception and
    display decoupled from disk I/O.
    """

    def __init__(
        self,
        record_queue: Queue[np.ndarray],
        stop_event: threading.Event,
        fps: int = DEFAULT_RECORD_FPS,
        extension: str = DEFAULT_VIDEO_EXTENSION,
    ) -> None:
        self._record_queue = record_queue
        self._stop_event = stop_event
        self._fps = fps
        self._extension = extension.lower()

        self._writer: cv2.VideoWriter | None = None
        self._recording = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._frame_count: int = 0
        self._output_path: str | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def output_path(self) -> str | None:
        with self._lock:
            return self._output_path

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._frame_count

    def start(self, frame_shape: tuple[int, int]) -> str:
        """Start recording to a new timestamped file.

        Args:
            frame_shape: ``(height, width)`` of the grayscale frames.

        Returns:
            The path of the created video file.

        Raises:
            RuntimeError: if recording is already active.
        """
        with self._lock:
            if self._recording:
                raise RuntimeError("Recording is already active")

            output_path = next_filename(VIDEO_DIR, "video", self._extension)
            fourcc = cv2.VideoWriter_fourcc(
                *(
                    VIDEO_FOURCC_MP4
                    if self._extension == ".mp4"
                    else VIDEO_FOURCC_AVI
                )
            )
            height, width = frame_shape
            writer = cv2.VideoWriter(str(output_path), fourcc, self._fps, (width, height), isColor=False)
            if not writer.isOpened():
                writer.release()
                raise RuntimeError(f"Failed to open video writer: {output_path}")

            self._writer = writer
            self._output_path = str(output_path)
            self._frame_count = 0
            self._recording = True

        self._thread = threading.Thread(target=self._run, name="VideoRecorder", daemon=True)
        self._thread.start()
        return self._output_path

    def stop(self) -> None:
        """Stop the current recording."""
        with self._lock:
            if not self._recording:
                return
            self._recording = False

        # Signal the worker to drain and exit.
        self._record_queue.put(None, block=True)

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        with self._lock:
            if self._writer is not None:
                self._writer.release()
                self._writer = None

    def _run(self) -> None:
        """Worker loop that writes frames to disk."""
        while not self._stop_event.is_set():
            try:
                frame = self._record_queue.get(timeout=0.05)
            except Empty:
                with self._lock:
                    if not self._recording:
                        break
                continue

            if frame is None:
                break

            with self._lock:
                if self._writer is None or not self._recording:
                    break
                self._writer.write(frame)
                self._frame_count += 1

    def toggle(self, frame_shape: tuple[int, int]) -> str | None:
        """Start recording if stopped, or stop if already recording.

        Returns:
            The output path when starting, or ``None`` when stopping.
        """
        if self.is_recording:
            self.stop()
            return None
        return self.start(frame_shape)
