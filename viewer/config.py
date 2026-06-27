"""Application configuration and constants."""

from __future__ import annotations

from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

FRAME_HEADER: Final[bytes] = b"\xAA\x55"
FRAME_TAIL: Final[bytes] = b"\x55\xAA"

PROTOCOL_VERSION: Final[int] = 0x01

# Fixed header payload size in bytes:
# Version(1) + Counter(4) + Width(2) + Height(2) + PixelFormat(1) + PayloadLength(4)
HEADER_FIELDS_SIZE: Final[int] = 14

# Known expected payload for the target camera.
EXPECTED_WIDTH: Final[int] = 188
EXPECTED_HEIGHT: Final[int] = 120
EXPECTED_PAYLOAD_LENGTH: Final[int] = EXPECTED_WIDTH * EXPECTED_HEIGHT

# CRC16 field (2 bytes) + frame tail (2 bytes)
CRC_TAIL_SIZE: Final[int] = 4

GRAYSCALE_FORMAT: Final[int] = 0x01

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent
SCREENSHOT_DIR: Final[Path] = PROJECT_ROOT / "Screenshots"
VIDEO_DIR: Final[Path] = PROJECT_ROOT / "Videos"

# ---------------------------------------------------------------------------
# Serial defaults
# ---------------------------------------------------------------------------

DEFAULT_BAUD_RATE: Final[int] = 921600
SUPPORTED_BAUD_RATES: Final[tuple[int, ...]] = (921600, 1500000, 2000000)
DEFAULT_SERIAL_TIMEOUT_S: Final[float] = 0.1
DEFAULT_READ_CHUNK_SIZE: Final[int] = 4096

# ---------------------------------------------------------------------------
# Display defaults
# ---------------------------------------------------------------------------

DEFAULT_DISPLAY_SCALE: Final[int] = 4
DISPLAY_WINDOW_NAME: Final[str] = "UART Camera Stream"
TARGET_FPS: Final[int] = 60
DISPLAY_INTERVAL_MS: Final[int] = 1  # cv2.waitKey delay; 1 ms keeps UI responsive.

# ---------------------------------------------------------------------------
# Threading / queue defaults
# ---------------------------------------------------------------------------

RAW_QUEUE_MAXSIZE: Final[int] = 8
FRAME_QUEUE_MAXSIZE: Final[int] = 4
RECORD_QUEUE_MAXSIZE: Final[int] = 8

# ---------------------------------------------------------------------------
# Recording defaults
# ---------------------------------------------------------------------------

VIDEO_FOURCC_AVI: Final[str] = "XVID"
VIDEO_FOURCC_MP4: Final[str] = "mp4v"
DEFAULT_VIDEO_EXTENSION: Final[str] = ".avi"
DEFAULT_RECORD_FPS: Final[int] = 30

# ---------------------------------------------------------------------------
# CRC16-CCITT parameters
# ---------------------------------------------------------------------------

CRC16_POLYNOMIAL: Final[int] = 0x1021
CRC16_INITIAL_VALUE: Final[int] = 0xFFFF
