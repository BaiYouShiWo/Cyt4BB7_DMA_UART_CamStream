"""OpenCV image display and keyboard handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np

from config import DISPLAY_INTERVAL_MS, DISPLAY_WINDOW_NAME, DEFAULT_DISPLAY_SCALE, SCREENSHOT_DIR
from utils import next_filename


class DisplayCommand:
    """Base class for keyboard-driven display commands."""


@dataclass(frozen=True)
class ScreenshotCommand(DisplayCommand):
    """User requested a screenshot."""

    path: Path


@dataclass(frozen=True)
class ToggleRecordingCommand(DisplayCommand):
    """User requested to start/stop video recording."""


@dataclass(frozen=True)
class TogglePauseCommand(DisplayCommand):
    """User requested to pause/resume the live display."""


@dataclass(frozen=True)
class ExitCommand(DisplayCommand):
    """User requested to exit the application."""


class ImageDisplay:
    """Manage the OpenCV window, scaling, and keyboard input.

    This class is intentionally kept simple and runs on the main thread.
    It does not perform any serial I/O.
    """

    ESC_KEY: Final[int] = 27
    S_KEY: Final[int] = ord("s")
    R_KEY: Final[int] = ord("r")
    SPACE_KEY: Final[int] = 32

    def __init__(self, scale: int = DEFAULT_DISPLAY_SCALE) -> None:
        self._scale = max(1, scale)
        self._window_created = False
        self._last_key: int = -1
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def create_window(self) -> None:
        """Create the OpenCV display window."""
        cv2.namedWindow(DISPLAY_WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
        self._window_created = True

    def destroy(self) -> None:
        """Destroy the OpenCV window."""
        if self._window_created:
            cv2.destroyWindow(DISPLAY_WINDOW_NAME)
            self._window_created = False

    def show(self, image: np.ndarray) -> DisplayCommand | None:
        """Display ``image`` and process one keyboard event.

        Args:
            image: Grayscale image to display.

        Returns:
            A command object if the user pressed a recognized key, otherwise ``None``.
        """
        scaled = self._scale_image(image)
        cv2.imshow(DISPLAY_WINDOW_NAME, scaled)

        key = cv2.waitKey(DISPLAY_INTERVAL_MS) & 0xFF
        if key == 255:
            return None

        self._last_key = key

        if key == self.ESC_KEY:
            return ExitCommand()
        if key == self.S_KEY:
            return self._save_screenshot(image)
        if key == self.R_KEY:
            return ToggleRecordingCommand()
        if key == self.SPACE_KEY:
            self._paused = not self._paused
            return TogglePauseCommand()

        return None

    def _scale_image(self, image: np.ndarray) -> np.ndarray:
        """Scale ``image`` using nearest-neighbor interpolation."""
        if self._scale == 1:
            return image
        height, width = image.shape[:2]
        return cv2.resize(
            image,
            (width * self._scale, height * self._scale),
            interpolation=cv2.INTER_NEAREST,
        )

    def _save_screenshot(self, image: np.ndarray) -> ScreenshotCommand:
        """Save ``image`` as a PNG and return the command."""
        path = next_filename(SCREENSHOT_DIR, "frame", ".png")
        success = cv2.imwrite(str(path), image)
        if success:
            print(f"[Display] Screenshot saved: {path}")
        else:
            print(f"[Display] Failed to save screenshot: {path}")
        return ScreenshotCommand(path=path)
