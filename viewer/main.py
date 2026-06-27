"""UART camera viewer main entry point."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from typing import Final

import cv2
import numpy as np
from serial.tools import list_ports

from config import (
    DEFAULT_BAUD_RATE,
    DEFAULT_DISPLAY_SCALE,
    EXPECTED_HEIGHT,
    EXPECTED_WIDTH,
    FRAME_QUEUE_MAXSIZE,
    RAW_QUEUE_MAXSIZE,
    RECORD_QUEUE_MAXSIZE,
    SCREENSHOT_DIR,
    SUPPORTED_BAUD_RATES,
    VIDEO_DIR,
)
from frame_parser import FrameParser, ParserStats
from image_display import (
    DisplayCommand,
    ExitCommand,
    ImageDisplay,
    ScreenshotCommand,
    TogglePauseCommand,
    ToggleRecordingCommand,
)
from image_protocol import Frame
from serial_receiver import SerialReceiver
from utils import ensure_directory
from video_recorder import VideoRecorder


class Application:
    """Top-level application orchestrator.

    Responsibilities:
        - Parse command-line arguments or interactively select serial settings.
        - Create and start worker threads (serial receiver, frame parser).
        - Run the OpenCV display loop on the main thread.
        - Handle keyboard commands (screenshot, recording, pause, exit).
        - Print periodic statistics to the console.
    """

    STATS_INTERVAL_S: Final[float] = 2.0

    def __init__(self, port: str, baud_rate: int, scale: int) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.scale = scale

        self._stop_event = threading.Event()
        self._raw_queue: queue.Queue[bytes] = queue.Queue(maxsize=RAW_QUEUE_MAXSIZE)
        self._frame_queue: queue.Queue[Frame] = queue.Queue(maxsize=FRAME_QUEUE_MAXSIZE)
        self._record_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=RECORD_QUEUE_MAXSIZE)
        self._parser_stats = ParserStats()

        self._serial_receiver = SerialReceiver(
            port=self.port,
            baud_rate=self.baud_rate,
            raw_queue=self._raw_queue,
            stop_event=self._stop_event,
            on_disconnect=self._on_serial_disconnect,
        )
        self._frame_parser = FrameParser(
            raw_queue=self._raw_queue,
            frame_queue=self._frame_queue,
            stop_event=self._stop_event,
            stats=self._parser_stats,
        )
        self._video_recorder = VideoRecorder(
            record_queue=self._record_queue,
            stop_event=self._stop_event,
        )
        self._display = ImageDisplay(scale=self.scale)

        self._running = False
        self._paused = False
        self._last_frame_counter: int | None = None
        self._last_frame_image: np.ndarray | None = None
        self._dropped_frames = 0
        self._last_stats_time = time.monotonic()
        self._fps_counter = 0
        self._last_fps_time = time.monotonic()
        self._current_fps = 0.0

    def _on_serial_disconnect(self) -> None:
        """Callback invoked by the serial receiver when the port is lost."""
        self._running = False

    def _start_workers(self) -> bool:
        """Open the serial port and start background threads.

        Returns:
            ``True`` if startup succeeded.
        """
        self._serial_receiver.start()

        # Wait briefly for the port to open and confirm health.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self._serial_receiver.connected:
                break
            if self._serial_receiver.connection_error is not None:
                print(
                    f"[App] Failed to open {self.port}: "
                    f"{self._serial_receiver.connection_error}"
                )
                self._stop_event.set()
                self._serial_receiver.join(timeout=1.0)
                return False
            time.sleep(0.05)
        else:
            print(f"[App] Timeout waiting for {self.port} to open")
            self._stop_event.set()
            self._serial_receiver.join(timeout=1.0)
            return False

        self._frame_parser.start()
        print(f"[App] Connected {self.port}")
        print(f"[App] {self.baud_rate} baud")
        return True

    def _stop_workers(self) -> None:
        """Signal all workers to stop and wait for them."""
        self._stop_event.set()

        # Wake the parser so it exits promptly.
        try:
            self._raw_queue.put(None, block=False)
        except queue.Full:
            pass

        self._video_recorder.stop()
        self._serial_receiver.stop()

        self._serial_receiver.join(timeout=1.0)
        self._frame_parser.join(timeout=1.0)

    def _consume_frame(self) -> Frame | None:
        """Retrieve the next frame from the queue without blocking.

        Returns:
            A :class:`Frame` or ``None`` if no frame is available.
        """
        try:
            return self._frame_queue.get(block=False)
        except queue.Empty:
            return None

    def _update_frame_counter(self, frame: Frame) -> None:
        """Track frame counter continuity for dropped-frame statistics."""
        if self._last_frame_counter is not None:
            expected = (self._last_frame_counter + 1) & 0xFFFFFFFF
            if frame.counter != expected:
                gap = (frame.counter - expected) & 0xFFFFFFFF
                if gap < 0x7FFFFFFF:
                    self._dropped_frames += gap
        self._last_frame_counter = frame.counter

    def _update_fps(self) -> None:
        """Recompute the displayed FPS every second."""
        now = time.monotonic()
        self._fps_counter += 1
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._current_fps = self._fps_counter / elapsed
            self._fps_counter = 0
            self._last_fps_time = now

    def _maybe_enqueue_for_recording(self, frame: Frame) -> None:
        """Push a copy of the frame to the recorder if recording is active."""
        if not self._video_recorder.is_recording:
            return
        try:
            # VideoWriter expects grayscale frames to be (H, W) or (H, W, 1).
            # We keep (H, W) and let the recorder pass isColor=False.
            self._record_queue.put(frame.image, block=False)
        except queue.Full:
            # Recording cannot keep up; drop the frame rather than block.
            pass

    def _print_stats(self) -> None:
        """Print console statistics at regular intervals."""
        now = time.monotonic()
        if now - self._last_stats_time < self.STATS_INTERVAL_S:
            return
        self._last_stats_time = now

        stats = self._parser_stats.snapshot()
        print(
            f"[Stats] FPS={self._current_fps:.1f} "
            f"Frames={stats['frames_ok']} "
            f"Counter={self._last_frame_counter} "
            f"Dropped={self._dropped_frames} "
            f"CRC_Err={stats['crc_errors']} "
            f"Tail_Err={stats['tail_errors']} "
            f"SyncLoss={stats['sync_losses']}"
        )

    def _handle_command(self, command: DisplayCommand | None) -> bool:
        """Process a keyboard command.

        Returns:
            ``False`` if the application should exit.
        """
        if command is None:
            return True

        if isinstance(command, ExitCommand):
            return False

        if isinstance(command, ScreenshotCommand):
            return True

        if isinstance(command, TogglePauseCommand):
            self._paused = self._display.paused
            state = "paused" if self._paused else "resumed"
            print(f"[App] Display {state}")
            return True

        if isinstance(command, ToggleRecordingCommand):
            try:
                if self._video_recorder.is_recording:
                    self._video_recorder.stop()
                    print("[App] Recording stopped")
                else:
                    # We need a frame shape to start the writer. If no frame has
                    # been received yet, we cannot start recording.
                    if self._last_frame_counter is None:
                        print("[App] Cannot start recording: no frame received yet")
                    else:
                        # Use the most recent frame's shape. Height/width are
                        # consistent for this camera.
                        shape = (
                            self._last_frame_image.shape
                            if self._last_frame_image is not None
                            else (EXPECTED_HEIGHT, EXPECTED_WIDTH)
                        )
                        path = self._video_recorder.start(shape)
                        print(f"[App] Recording started: {path}")
            except Exception as exc:
                print(f"[App] Recording error: {exc}")
            return True

        return True

    def run(self) -> int:
        """Main application loop.

        Returns:
            Process exit code.
        """
        ensure_directory(SCREENSHOT_DIR)
        ensure_directory(VIDEO_DIR)

        if not self._start_workers():
            return 1

        self._running = True
        self._display.create_window()

        try:
            while self._running:
                frame = self._consume_frame()

                if frame is not None:
                    self._update_frame_counter(frame)
                    self._update_fps()
                    self._maybe_enqueue_for_recording(frame)

                    if not self._paused:
                        self._last_frame_image = frame.image
                        command = self._display.show(frame.image)
                    else:
                        # While paused, still service the window event queue so
                        # that keyboard input is processed. Keep showing the
                        # frame that was live when pause was activated.
                        image = self._last_frame_image or frame.image
                        command = self._display.show(image)
                    if not self._handle_command(command):
                        break
                else:
                    # No frame available; keep the window responsive.
                    image = self._last_frame_image
                    if image is None:
                        image = np.zeros(
                            (EXPECTED_HEIGHT, EXPECTED_WIDTH), dtype=np.uint8
                        )
                    command = self._display.show(image)
                    if not self._handle_command(command):
                        break
                    time.sleep(0.005)

                self._print_stats()

                if not self._serial_receiver.connected and not self._stop_event.is_set():
                    print("[App] Serial connection lost; exiting...")
                    break
        except KeyboardInterrupt:
            print("[App] Interrupted by user")
        finally:
            self._display.destroy()
            self._stop_workers()
            print("[App] Disconnected")

        return 0


def _list_serial_ports() -> list[str]:
    """Return a list of available serial port names."""
    return [port.device for port in list_ports.comports()]


def _choose_port() -> str:
    """Interactively select a serial port."""
    ports = _list_serial_ports()
    if not ports:
        print("No serial ports detected.")
        port = input("Enter COM port manually (e.g. COM5): ").strip()
        return port

    print("Available serial ports:")
    for idx, port in enumerate(ports, start=1):
        print(f"  {idx}. {port}")

    while True:
        choice = input("Select port number: ").strip()
        try:
            index = int(choice) - 1
            if 0 <= index < len(ports):
                return ports[index]
        except ValueError:
            pass
        print("Invalid selection. Please try again.")


def _choose_baud() -> int:
    """Interactively select a baud rate."""
    print("Supported baud rates:")
    for idx, baud in enumerate(SUPPORTED_BAUD_RATES, start=1):
        mark = " (default)" if baud == DEFAULT_BAUD_RATE else ""
        print(f"  {idx}. {baud}{mark}")

    while True:
        choice = input("Select baud rate number: ").strip()
        if not choice:
            return DEFAULT_BAUD_RATE
        try:
            index = int(choice) - 1
            if 0 <= index < len(SUPPORTED_BAUD_RATES):
                return SUPPORTED_BAUD_RATES[index]
        except ValueError:
            pass
        print("Invalid selection. Please try again.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UART camera stream viewer.",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=str,
        default=None,
        help="Serial port name (e.g. COM5). If omitted, an interactive prompt is shown.",
    )
    parser.add_argument(
        "--baud",
        "-b",
        type=int,
        default=DEFAULT_BAUD_RATE,
        choices=SUPPORTED_BAUD_RATES,
        help=f"Serial baud rate (default {DEFAULT_BAUD_RATE}).",
    )
    parser.add_argument(
        "--scale",
        "-s",
        type=int,
        default=DEFAULT_DISPLAY_SCALE,
        help=f"Display scaling factor (default {DEFAULT_DISPLAY_SCALE}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    port = args.port if args.port else _choose_port()
    baud_rate = args.baud
    scale = args.scale

    app = Application(port=port, baud_rate=baud_rate, scale=scale)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
