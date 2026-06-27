"""Frame parser with automatic synchronization recovery."""

from __future__ import annotations

import struct
import threading
from enum import Enum, auto
from queue import Empty, Full, Queue

import numpy as np

from config import (
    CRC16_INITIAL_VALUE,
    CRC16_POLYNOMIAL,
    CRC_TAIL_SIZE,
    FRAME_HEADER,
    FRAME_TAIL,
    HEADER_FIELDS_SIZE,
)
from image_protocol import Frame, FrameHeader, ProtocolError, build_frame, compute_crc16


class ParserState(Enum):
    """Internal frame-parser state machine states."""

    SEARCH_HEADER = auto()
    READ_FIELDS = auto()
    READ_PAYLOAD = auto()
    READ_CRC_AND_TAIL = auto()


class FrameParser(threading.Thread):
    """Consume raw bytes and emit decoded frames.

    The parser runs in its own thread. It reads chunks from ``raw_queue``,
    assembles a byte buffer, searches for frame headers, validates protocol
    fields, checks the CRC, and places complete :class:`Frame` objects into
    ``frame_queue``.

    On any error the parser discards the bad data, re-synchronizes on the next
    header, and continues operating.
    """

    def __init__(
        self,
        raw_queue: Queue[bytes],
        frame_queue: Queue[Frame],
        stop_event: threading.Event,
        stats: "ParserStats",
        max_buffer_size: int = 256 * 1024,
    ) -> None:
        super().__init__(name="FrameParser", daemon=True)
        self._raw_queue = raw_queue
        self._frame_queue = frame_queue
        self._stop_event = stop_event
        self._stats = stats
        self._max_buffer_size = max_buffer_size

        self._buffer = bytearray()
        self._state = ParserState.SEARCH_HEADER
        self._header: FrameHeader | None = None
        self._payload = bytearray()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._raw_queue.get(timeout=0.05)
            except Empty:
                continue

            if chunk is None:
                # Sentinel used to drain the parser cleanly.
                break

            self._stats.bytes_received += len(chunk)
            self._buffer.extend(chunk)

            # Prevent unbounded growth on a completely garbage stream.
            if len(self._buffer) > self._max_buffer_size:
                self._trim_buffer()

            self._process_buffer()

    def _trim_buffer(self) -> None:
        """Drop oldest bytes when the buffer grows too large."""
        excess = len(self._buffer) - self._max_buffer_size
        # Keep at least the tail end where a header might reside.
        keep = max(HEADER_FIELDS_SIZE + CRC_TAIL_SIZE, len(self._buffer) - excess)
        del self._buffer[: len(self._buffer) - keep]
        self._state = ParserState.SEARCH_HEADER
        self._header = None
        self._payload.clear()
        self._stats.sync_losses += 1

    def _process_buffer(self) -> None:
        """Run the state machine until the buffer is exhausted."""
        while True:
            if self._state is ParserState.SEARCH_HEADER:
                if not self._search_header():
                    return
            elif self._state is ParserState.READ_FIELDS:
                if not self._read_fields():
                    return
            elif self._state is ParserState.READ_PAYLOAD:
                if not self._read_payload():
                    return
            elif self._state is ParserState.READ_CRC_AND_TAIL:
                if not self._read_crc_and_tail():
                    return
            else:
                # Defensive fallback.
                self._reset_state()

    def _search_header(self) -> bool:
        """Find ``FRAME_HEADER`` in the buffer.

        Returns:
            ``True`` if a header was found and the state advanced.
        """
        header_idx = self._buffer.find(FRAME_HEADER)
        if header_idx == -1:
            # Keep only the last byte in case it is the start of a header.
            if len(self._buffer) >= len(FRAME_HEADER):
                self._buffer = self._buffer[-(len(FRAME_HEADER) - 1) :]
            return False

        if header_idx > 0:
            self._stats.bytes_discarded += header_idx
            self._stats.sync_losses += 1

        del self._buffer[:header_idx]
        self._state = ParserState.READ_FIELDS
        return True

    def _read_fields(self) -> bool:
        """Parse header fields once they are fully buffered.

        Returns:
            ``True`` if fields were read and the state advanced.
        """
        required = len(FRAME_HEADER) + HEADER_FIELDS_SIZE
        if len(self._buffer) < required:
            return False

        fields_data = bytes(self._buffer[len(FRAME_HEADER) : required])
        try:
            self._header = FrameHeader.from_bytes(fields_data)
            self._header.validate()
        except ProtocolError as exc:
            self._stats.invalid_packets += 1
            self._discard_one_byte_and_resync()
            return True  # Try again from the same buffer.

        self._state = ParserState.READ_PAYLOAD
        return True

    def _read_payload(self) -> bool:
        """Read the image payload once it is fully buffered.

        Returns:
            ``True`` if the payload was read and the state advanced.
        """
        assert self._header is not None
        payload_start = len(FRAME_HEADER) + HEADER_FIELDS_SIZE
        payload_end = payload_start + self._header.payload_length

        if len(self._buffer) < payload_end:
            return False

        self._payload = self._buffer[payload_start:payload_end]
        self._state = ParserState.READ_CRC_AND_TAIL
        return True

    def _read_crc_and_tail(self) -> bool:
        """Validate CRC and tail, then emit a frame.

        Returns:
            ``True`` if the CRC/tail block was processed and the state reset.
        """
        assert self._header is not None
        payload_start = len(FRAME_HEADER) + HEADER_FIELDS_SIZE
        payload_end = payload_start + self._header.payload_length
        frame_end = payload_end + CRC_TAIL_SIZE

        if len(self._buffer) < frame_end:
            return False

        crc_tail = bytes(self._buffer[payload_end:frame_end])
        computed_crc = compute_crc16(
            bytes(self._buffer[:payload_end]),
            poly=CRC16_POLYNOMIAL,
            init=CRC16_INITIAL_VALUE,
        )
        received_crc = struct.unpack("<H", crc_tail[:2])[0]

        if computed_crc != received_crc:
            self._stats.crc_errors += 1
            self._discard_one_byte_and_resync()
            return True

        if crc_tail[2:] != FRAME_TAIL:
            self._stats.tail_errors += 1
            self._discard_one_byte_and_resync()
            return True

        try:
            frame = build_frame(self._header, bytes(self._payload))
            self._frame_queue.put(frame, block=False)
            self._stats.frames_ok += 1
        except Full:
            # Display thread cannot keep up; frame is valid but dropped.
            self._stats.frames_ok += 1
            self._stats.sync_losses += 1
        except Exception:  # pragma: no cover - defensive
            self._stats.invalid_packets += 1

        del self._buffer[:frame_end]
        self._reset_state()
        return True

    def _discard_one_byte_and_resync(self) -> None:
        """Drop the leading byte and restart header search."""
        if self._buffer:
            del self._buffer[0]
        self._reset_state()

    def _reset_state(self) -> None:
        """Return the state machine to header-search mode."""
        self._state = ParserState.SEARCH_HEADER
        self._header = None
        self._payload = bytearray()


class ParserStats:
    """Thread-safe statistics for the frame parser."""

    __slots__ = (
        "_lock",
        "bytes_received",
        "bytes_discarded",
        "frames_ok",
        "crc_errors",
        "tail_errors",
        "invalid_packets",
        "sync_losses",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.bytes_received: int = 0
        self.bytes_discarded: int = 0
        self.frames_ok: int = 0
        self.crc_errors: int = 0
        self.tail_errors: int = 0
        self.invalid_packets: int = 0
        self.sync_losses: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return a copy of the current statistics."""
        with self._lock:
            return {
                "bytes_received": self.bytes_received,
                "bytes_discarded": self.bytes_discarded,
                "frames_ok": self.frames_ok,
                "crc_errors": self.crc_errors,
                "tail_errors": self.tail_errors,
                "invalid_packets": self.invalid_packets,
                "sync_losses": self.sync_losses,
            }

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a statistic by ``value``."""
        with self._lock:
            current = getattr(self, name, 0)
            setattr(self, name, current + value)
