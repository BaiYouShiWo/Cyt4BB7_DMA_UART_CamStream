"""Serial port receiver thread."""

from __future__ import annotations

import threading
import time
from queue import Queue
from typing import Callable

import serial
from serial import SerialException, SerialTimeoutException

from config import DEFAULT_READ_CHUNK_SIZE, DEFAULT_SERIAL_TIMEOUT_S


class SerialReceiver(threading.Thread):
    """Read raw bytes from a serial port and push them into a queue.

    The receiver runs in its own thread. It opens the requested serial port,
    reads chunks of bytes, and places them into ``raw_queue``. It detects
    disconnections by monitoring read errors and the port's presence.

    Attributes:
        port: Serial port name (e.g. ``"COM5"``).
        baud_rate: Baud rate in use.
        connected: ``True`` while the serial port is open and healthy.
        disconnected_at: Monotonic timestamp when the port was lost, or ``None``.
    """

    def __init__(
        self,
        port: str,
        baud_rate: int,
        raw_queue: Queue[bytes],
        stop_event: threading.Event,
        chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
        read_timeout: float = DEFAULT_SERIAL_TIMEOUT_S,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(name="SerialReceiver", daemon=True)
        self.port = port
        self.baud_rate = baud_rate
        self._raw_queue = raw_queue
        self._stop_event = stop_event
        self._chunk_size = chunk_size
        self._read_timeout = read_timeout
        self._on_disconnect = on_disconnect

        self._serial: serial.Serial | None = None
        self.connected = False
        self.disconnected_at: float | None = None
        self._connection_error: Exception | None = None

    @property
    def connection_error(self) -> Exception | None:
        """The exception that caused the last disconnect, if any."""
        return self._connection_error

    def _open(self) -> None:
        """Open the serial port with the configured parameters."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._read_timeout,
                write_timeout=0,
            )
            self.connected = True
            self._connection_error = None
        except SerialException as exc:
            self._connection_error = exc
            self.connected = False
            raise

    def _close(self) -> None:
        """Close the serial port cleanly."""
        self.connected = False
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except SerialException:
                pass
            finally:
                self._serial = None

    def run(self) -> None:
        """Main receiver loop."""
        try:
            self._open()
        except SerialException:
            return

        try:
            while not self._stop_event.is_set():
                if self._serial is None or not self._serial.is_open:
                    self._handle_disconnect(SerialException("Serial port closed"))
                    return

                try:
                    chunk = self._serial.read(self._chunk_size)
                except (SerialException, SerialTimeoutException, OSError) as exc:
                    self._handle_disconnect(exc)
                    return

                if chunk:
                    try:
                        self._raw_queue.put(chunk, block=False)
                    except Exception:
                        # Queue full: drop the chunk. The parser stats will
                        # eventually reflect the lost sync.
                        pass
                else:
                    # Timeout with no data: yield briefly to keep the thread
                    # responsive to stop requests.
                    time.sleep(0.001)
        finally:
            self._close()

    def _handle_disconnect(self, exc: Exception) -> None:
        """Record disconnect state and notify the owner."""
        if self.connected:
            self.connected = False
            self.disconnected_at = time.monotonic()
            self._connection_error = exc
            print(f"[Serial] Disconnected from {self.port}: {exc}")
            if self._on_disconnect is not None:
                try:
                    self._on_disconnect()
                except Exception:
                    pass
        self._close()

    def stop(self) -> None:
        """Request the receiver to stop and close the port."""
        self._stop_event.set()
        self._close()
