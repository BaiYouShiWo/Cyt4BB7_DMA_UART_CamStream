"""Image protocol definitions and helpers."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Final

import numpy as np

from config import (
    CRC_TAIL_SIZE,
    EXPECTED_PAYLOAD_LENGTH,
    FRAME_HEADER,
    FRAME_TAIL,
    GRAYSCALE_FORMAT,
    HEADER_FIELDS_SIZE,
)


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded camera frame."""

    counter: int
    width: int
    height: int
    pixel_format: int
    payload_length: int
    image: np.ndarray
    received_at: float



class ProtocolError(Exception):
    """Raised when a frame violates the protocol."""


class FrameHeader:
    """Parsed fixed-length frame header fields."""

    STRUCT_FORMAT: Final[str] = "<B I H H B I"  # little-endian
    SIZE: Final[int] = HEADER_FIELDS_SIZE

    __slots__ = (
        "version",
        "counter",
        "width",
        "height",
        "pixel_format",
        "payload_length",
    )

    def __init__(
        self,
        version: int,
        counter: int,
        width: int,
        height: int,
        pixel_format: int,
        payload_length: int,
    ) -> None:
        self.version = version
        self.counter = counter
        self.width = width
        self.height = height
        self.pixel_format = pixel_format
        self.payload_length = payload_length

    @classmethod
    def from_bytes(cls, data: bytes) -> "FrameHeader":
        if len(data) != cls.SIZE:
            raise ProtocolError(
                f"Header field payload must be {cls.SIZE} bytes, got {len(data)}"
            )
        (
            version,
            counter,
            width,
            height,
            pixel_format,
            payload_length,
        ) = struct.unpack(cls.STRUCT_FORMAT, data)
        return cls(
            version=version,
            counter=counter,
            width=width,
            height=height,
            pixel_format=pixel_format,
            payload_length=payload_length,
        )

    def validate(self) -> None:
        """Validate header values.

        Raises:
            ProtocolError: if any field is out of the expected range.
        """
        if self.pixel_format != GRAYSCALE_FORMAT:
            raise ProtocolError(
                f"Unsupported pixel format 0x{self.pixel_format:02X}; "
                f"expected 0x{GRAYSCALE_FORMAT:02X} (8-bit grayscale)"
            )
        if self.width <= 0 or self.height <= 0:
            raise ProtocolError(
                f"Invalid frame dimensions: {self.width}x{self.height}"
            )
        if self.payload_length != EXPECTED_PAYLOAD_LENGTH:
            raise ProtocolError(
                f"Unexpected payload length {self.payload_length}; "
                f"expected {EXPECTED_PAYLOAD_LENGTH}"
            )


def compute_crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """Compute CRC16-CCITT over ``data``.

    Args:
        data: Input bytes.
        poly: Generator polynomial (default 0x1021).
        init: Initial CRC value (default 0xFFFF).

    Returns:
        The computed 16-bit CRC value.
    """
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def pack_frame_for_crc(header: FrameHeader, payload: bytes) -> bytes:
    """Return the byte sequence over which the CRC is calculated.

    The CRC covers the frame header marker, the header fields, and the payload.
    The CRC field and tail are excluded.
    """
    fields = struct.pack(
        FrameHeader.STRUCT_FORMAT,
        header.version,
        header.counter,
        header.width,
        header.height,
        header.pixel_format,
        header.payload_length,
    )
    return FRAME_HEADER + fields + payload


def build_frame(header: FrameHeader, payload: bytes) -> Frame:
    """Construct a :class:`Frame` from a validated header and payload."""
    image = np.frombuffer(payload, dtype=np.uint8).reshape(
        (header.height, header.width)
    )
    return Frame(
        counter=header.counter,
        width=header.width,
        height=header.height,
        pixel_format=header.pixel_format,
        payload_length=header.payload_length,
        image=image,
        received_at=time.monotonic(),
    )
