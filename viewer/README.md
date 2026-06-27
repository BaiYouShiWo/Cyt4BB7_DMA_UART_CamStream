# UART Camera Viewer

A lightweight Python engineering tool for receiving and displaying grayscale image frames from an embedded device over a high-speed UART connection.

## Features

- Serial connection with selectable COM port and baud rate (921600, 1500000, 2000000)
- Robust frame parser with automatic synchronization recovery
- Real-time OpenCV display with nearest-neighbor scaling
- Screenshot capture (PNG)
- Video recording (AVI/MP4) in a background thread
- Multithreaded architecture for stable long-term operation
- Console statistics: FPS, frame counter, dropped frames, CRC errors, sync losses

## Project Structure

```
viewer/
├── config.py            # Protocol and application constants
├── image_protocol.py    # Frame dataclass, header parsing, CRC16
├── frame_parser.py      # Frame parser state machine with sync recovery
├── serial_receiver.py   # Serial port reader thread
├── image_display.py     # OpenCV display and keyboard handling
├── video_recorder.py    # Background video recorder
├── utils.py             # Timestamp and file helpers
├── main.py              # Application entry point and orchestration
├── requirements.txt
└── README.md
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Test

Run the parser self-test without any hardware:

```bash
python test_parser.py
```

## Usage

Interactive port selection:

```bash
python main.py
```

Specify port and baud rate directly:

```bash
python main.py -p COM5 -b 921600
```

Adjust display scale:

```bash
python main.py -p COM5 -b 1500000 -s 3
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `ESC` | Exit the program |
| `S` | Save the current frame as PNG |
| `R` | Start or stop video recording |
| `SPACE` | Pause or resume image display |

## Output Directories

- Screenshots: `viewer/Screenshots/`
- Videos: `viewer/Videos/`

Both directories are created automatically.

## Protocol Summary

Each frame uses the following binary format:

| Field | Size |
|-------|------|
| Header | 2 bytes (`0xAA 0x55`) |
| Protocol Version | 1 byte |
| Frame Counter | 4 bytes (little-endian `uint32`) |
| Width | 2 bytes (little-endian `uint16`) |
| Height | 2 bytes (little-endian `uint16`) |
| Pixel Format | 1 byte (`0x01` = 8-bit grayscale) |
| Payload Length | 4 bytes (little-endian `uint32`) |
| Image Payload | 188 × 120 bytes |
| CRC16 | 2 bytes (CRC16-CCITT, poly `0x1021`, init `0xFFFF`) |
| Frame Tail | 2 bytes (`0x55 0xAA`) |

CRC16 is computed over the header, header fields, and payload.
