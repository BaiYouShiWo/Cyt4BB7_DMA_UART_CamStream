"""Simple parser self-test using synthetic frames."""

from __future__ import annotations

import struct
import threading
import time
from queue import Queue

import numpy as np

from config import (
    CRC16_INITIAL_VALUE,
    CRC16_POLYNOMIAL,
    EXPECTED_HEIGHT,
    EXPECTED_WIDTH,
    FRAME_HEADER,
    FRAME_TAIL,
    GRAYSCALE_FORMAT,
    HEADER_FIELDS_SIZE,
)
from frame_parser import FrameParser, ParserStats
from image_protocol import compute_crc16


def build_frame_bytes(counter: int, width: int = EXPECTED_WIDTH, height: int = EXPECTED_HEIGHT) -> bytes:
    payload = np.arange(width * height, dtype=np.uint8).tobytes()
    fields = struct.pack(
        "<B I H H B I",
        0x01,  # version
        counter,
        width,
        height,
        GRAYSCALE_FORMAT,
        len(payload),
    )
    crc_data = FRAME_HEADER + fields + payload
    crc = compute_crc16(crc_data, poly=CRC16_POLYNOMIAL, init=CRC16_INITIAL_VALUE)
    return crc_data + struct.pack("<H", crc) + FRAME_TAIL


def main() -> None:
    raw_queue: Queue[bytes] = Queue()
    frame_queue: Queue = Queue()
    stats = ParserStats()

    stop_event = threading.Event()
    parser = FrameParser(raw_queue, frame_queue, stop_event, stats)
    parser.start()

    # Inject garbage, then a valid frame, then garbage, then another valid frame.
    raw_queue.put(b"\x00\x01\x02")
    raw_queue.put(build_frame_bytes(1))
    raw_queue.put(b"\xAA")  # partial header
    raw_queue.put(b"\x55" + build_frame_bytes(2)[2:])

    # Corrupted CRC frame followed by valid frame to verify recovery.
    bad_frame = bytearray(build_frame_bytes(3))
    bad_frame[-4] ^= 0xFF  # corrupt CRC byte
    raw_queue.put(bytes(bad_frame))
    raw_queue.put(build_frame_bytes(4))

    raw_queue.put(None)

    parser.join(timeout=2.0)

    frames = []
    while not frame_queue.empty():
        frames.append(frame_queue.get())

    print(f"Frames decoded: {len(frames)}")
    for frame in frames:
        print(f"  counter={frame.counter}, shape={frame.image.shape}")

    print(f"Parser stats: {stats.snapshot()}")
    assert len(frames) == 3, f"Expected 3 frames, got {len(frames)}"
    assert frames[0].counter == 1
    assert frames[1].counter == 2
    assert frames[2].counter == 4
    assert stats.snapshot()["crc_errors"] >= 1, "Expected at least one CRC error"
    print("Parser self-test passed.")


if __name__ == "__main__":
    main()
