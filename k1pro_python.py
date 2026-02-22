#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "hidapi",
#     "pillow",
# ]
# ///
"""
vsdinside k1-pro SDK - Python Implementation
Protocol reverse-engineered from USB capture (vsd-k1-pro.pcapng)
Same CRT+BAT protocol as Fifine D6, different parameters.

Usage:
    uv run k1pro_python.py
"""

import hid
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import io

# Device constants
VENDOR_ID = 0x5548
PRODUCT_ID = 0x1025
USAGE_PAGE = 0xffa0
REPORT_ID = 0x04
WRITE_SIZE = 1024   # Report ID (1) + data payload (1023)
DATA_SIZE = 1023    # Payload size per packet (excluding report ID)
IMAGE_SIZE = (64, 64)

# Timing constants (in seconds)
TIMING_BAT_HEADER = 0.01
TIMING_JPEG_CHUNK = 0.01
TIMING_STP_CMD = 0.01
TIMING_CONNECT = 0.05
KEEPALIVE_INTERVAL = 0.05  # Send images every 50ms (20fps) to stay in stream deck mode
CONNECT_INTERVAL = 10.0  # Send CONNECT heartbeat every 10s

# Protocol commands (from USB capture)
STP_COMMAND = b'\x43\x52\x54\x00\x00\x53\x54\x50\x00\x00'
CONNECT_COMMAND = b'\x43\x52\x54\x00\x00\x43\x4f\x4e\x4e\x45\x43\x54'  # CRT+CONNECT (heartbeat)
CLE_COMMAND = b'\x43\x52\x54\x00\x00\x43\x4c\x45\x00\x00\x00\xff'      # CRT+CLE
DIS_COMMAND = b'\x43\x52\x54\x00\x00\x44\x49\x53\x00\x00'               # CRT+DIS
WAKE_COMMAND = b'\x43\x52\x54\x00\x00\x77\x61\x6b\x65\x00'              # CRT+wake
LIG_COMMAND = b'\x43\x52\x54\x00\x00\x4c\x49\x47\x00\x00\x00\x19'       # CRT+LIG
QUCMD_COMMAND = b'\x43\x52\x54\x00\x00\x51\x55\x43\x4d\x44\x11\x11\x00\x11\x00\x11'  # CRT+QUCMD
CPOS_COMMAND = b'\x43\x52\x54\x00\x00\x43\x50\x4f\x53\x00\x4d'          # CRT+CPOS M

# Button index (0-5) -> protocol ID mapping
# Physical layout vs protocol IDs:
#   Physical: [B1][B2][B3]    Protocol: [5][3][1]
#             [B4][B5][B6]              [6][4][2]
BUTTON_ID_MAP = [5, 3, 1, 6, 4, 2]


class K1Pro:
    """
    vsdinside k1-pro controller

    Layout: 6 buttons + 3 knobs
    ┌────────────────────────────┐
    │  K1    K2    K3            │  Knobs (top)
    ├────┬────┬────┬────┬────┬───┤
    │ B1 │ B2 │ B3 │ B4 │ B5 │ B6│  Buttons
    └────┴────┴────┴────┴────┴───┘

    Button indices: 0-5 (6 buttons)
    Protocol: CRT+BAT (same as Fifine D6)
    Report ID: 4, Packet: 1024 bytes, Image: 64x64 JPEG
    """

    def __init__(self):
        self.connected = False
        self._control_path = None
        self._event_path = None
        self._button_images = {}  # Cache: button_index -> jpeg_data
        self._keepalive_thread = None
        self._keepalive_stop = threading.Event()
        self._control_lock = threading.Lock()  # Serialize access to control device

    @staticmethod
    def _map_button_for_image(button_index):
        """Map physical button index (0-5) to protocol ID.

        Physical: [B1][B2][B3][B4][B5][B6] -> Protocol: [5][3][1][6][4][2]
        """
        return BUTTON_ID_MAP[button_index]

    def _write_report(self, device, payload):
        """Write payload with Report ID 4, padded to 1024 bytes."""
        packet = bytearray(WRITE_SIZE)
        packet[0] = REPORT_ID
        packet[1:1 + len(payload)] = payload
        device.write(bytes(packet))

    def _open_control(self):
        """Open control endpoint with retry logic for macOS HID."""
        if self._control_path is None:
            for dev in hid.enumerate(VENDOR_ID, PRODUCT_ID):
                if dev['usage_page'] == USAGE_PAGE and dev['usage'] == 0x0001:
                    self._control_path = dev['path']
                    break
            if self._control_path is None:
                raise RuntimeError("Control endpoint not found. Is the device connected?")

        device = hid.device()

        # Retry opening with delays for macOS HID device release
        max_retries = 5
        for attempt in range(max_retries):
            try:
                device.open_path(self._control_path)
                return device
            except OSError as e:
                if attempt < max_retries - 1:
                    time.sleep(0.1)  # Wait 100ms for OS to release device
                else:
                    raise RuntimeError(f"Failed to open control device after {max_retries} attempts: {e}")

    def _open_events(self):
        """Open event endpoint (usage 0x0002)."""
        if self._event_path is None:
            for dev in hid.enumerate(VENDOR_ID, PRODUCT_ID):
                if dev['usage_page'] == USAGE_PAGE and dev['usage'] == 0x0002:
                    self._event_path = dev['path']
                    break
            if self._event_path is None:
                raise RuntimeError("Event endpoint not found. Is the device connected?")

        device = hid.device()
        device.open_path(self._event_path)
        return device

    def connect(self):
        """Connect to the k1-pro device."""
        print(f"Looking for k1-pro (VID: {VENDOR_ID:04x}, PID: {PRODUCT_ID:04x})...")

        matching_devices = [
            d for d in hid.enumerate()
            if d['vendor_id'] == VENDOR_ID and d['product_id'] == PRODUCT_ID
        ]

        if not matching_devices:
            raise RuntimeError(f"k1-pro device not found (VID: {VENDOR_ID:04x}, PID: {PRODUCT_ID:04x})")

        print(f"Found {len(matching_devices)} matching interface(s)")

        for device in matching_devices:
            if device.get('usage_page') == USAGE_PAGE:
                if device.get('usage') == 1:
                    self._control_path = device['path']
                elif device.get('usage') == 2:
                    self._event_path = device['path']

        if not self._control_path:
            raise RuntimeError("Control interface not found")

        # Send init sequence
        self.send_init()
        self.connected = True
        print("k1-pro connected and initialized\n")

    def send_init(self):
        """Initialize device to stream deck mode (VSD Craft sequence)."""
        with self._control_lock:
            device = self._open_control()
            try:
                # VSD Craft init sequence from USB capture
                self._write_report(device, DIS_COMMAND)
                time.sleep(0.001)
                self._write_report(device, WAKE_COMMAND)
                time.sleep(0.001)
                self._write_report(device, LIG_COMMAND)
                time.sleep(0.0001)
                self._write_report(device, QUCMD_COMMAND)
                time.sleep(0.0001)
                self._write_report(device, CPOS_COMMAND)
                time.sleep(0.002)
                self._write_report(device, LIG_COMMAND)
                time.sleep(0.001)
                self._write_report(device, CLE_COMMAND)
                time.sleep(0.001)
                self._write_report(device, STP_COMMAND)
                time.sleep(0.002)
            finally:
                device.close()

    def set_button_image(self, button_index, jpeg_data):
        """
        Send JPEG image to a button.

        Args:
            button_index: 0-based button index (0-5)
            jpeg_data: JPEG image data as bytes
        """
        if not self.connected:
            raise RuntimeError("Device not connected. Call connect() first.")

        if not 0 <= button_index < 6:
            raise ValueError(f"Invalid button index: {button_index} (must be 0-5)")

        self._button_images[button_index] = jpeg_data  # Cache for keepalive
        button_id = self._map_button_for_image(button_index)

        with self._control_lock:
            device = self._open_control()
            try:
                self._send_jpeg_to_button(device, button_id, jpeg_data)
            finally:
                device.close()

    def _send_jpeg_to_button(self, device, button_id, jpeg_data):
        """Send JPEG data to a button using BAT protocol.

        BAT header (same structure as Fifine D6):
          CRT\\x00\\x00BAT\\x00\\x00 + SIZE_BE16 + BUTTON_ID
        """
        size = len(jpeg_data)

        # BAT header: CRT\x00\x00BAT\x00\x00 + size (BE 16-bit) + button_id
        header = bytearray(13)
        header[0:10] = b'CRT\x00\x00BAT\x00\x00'
        header[10] = (size >> 8) & 0xFF  # Size high byte
        header[11] = size & 0xFF          # Size low byte
        header[12] = button_id

        self._write_report(device, header)
        time.sleep(TIMING_BAT_HEADER)

        # Send JPEG data in chunks (max DATA_SIZE bytes per packet)
        for i in range(0, len(jpeg_data), DATA_SIZE):
            chunk = jpeg_data[i:i + DATA_SIZE]
            self._write_report(device, chunk)
            time.sleep(TIMING_JPEG_CHUNK)

        # Send STP command (no HAN+DIS - k1-pro doesn't use them)
        self._write_report(device, STP_COMMAND)
        time.sleep(TIMING_STP_CMD)

    def set_multiple_images(self, images):
        """
        Set multiple button images efficiently.

        Args:
            images: List of (button_index, jpeg_data) tuples
        """
        if not self.connected:
            raise RuntimeError("Device not connected. Call connect() first.")

        with self._control_lock:
            device = self._open_control()
            try:
                for idx, (button_index, jpeg_data) in enumerate(images):
                    if not 0 <= button_index < 6:
                        print(f"Skipping invalid button index: {button_index}")
                        continue

                    button_id = self._map_button_for_image(button_index)
                    self._send_jpeg_to_button(device, button_id, jpeg_data)
                    print(f"Button {button_index + 1} updated ({idx + 1}/{len(images)})")
            finally:
                device.close()

    def read_button_event(self, timeout_ms=100, event_device=None):
        """
        Read button press/release events.

        Args:
            timeout_ms: Timeout in milliseconds
            event_device: Optional pre-opened event device

        Returns:
            (button_index, is_pressed) tuple or None if no event
            button_index is 0-based (0-5)
        """
        should_close = False
        if event_device is None:
            if not self._event_path:
                return None
            event_device = self._open_events()
            event_device.set_nonblocking(1)
            should_close = True

        try:
            # Read full report size to drain buffer properly
            data = event_device.read(WRITE_SIZE, timeout_ms)
            if not data or len(data) < 2:
                return None

            # Return raw event data for caller to interpret
            # data[0]=button_index, data[1]=is_pressed (or knob value)
            button_index = data[0]
            is_pressed = data[1] == 1

            return (button_index, is_pressed)
        finally:
            if should_close:
                event_device.close()

        return None

    @staticmethod
    def create_button_image(label, sublabel=None, bg_color="#000000"):
        """
        Create a 64x64 JPEG button image.

        Args:
            label: Main text to display
            sublabel: Optional second line of text
            bg_color: Background color (hex string)

        Returns:
            JPEG image data as bytes
        """
        img = Image.new('RGB', IMAGE_SIZE, bg_color)
        draw = ImageDraw.Draw(img)

        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18, index=1)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12, index=1)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        sz = IMAGE_SIZE[0]

        # Draw main label (centered)
        if label:
            bbox = draw.textbbox((0, 0), label, font=font_large)
            text_width = bbox[2] - bbox[0]
            x = (sz - text_width) // 2
            y = 15 if sublabel else 22
            draw.text((x, y), label, fill="black", font=font_large)

        # Draw sublabel if present
        if sublabel:
            bbox = draw.textbbox((0, 0), sublabel, font=font_small)
            sub_width = bbox[2] - bbox[0]
            sub_x = (sz - sub_width) // 2
            draw.text((sub_x, 38), sublabel, fill="black", font=font_small)

        # Rotate 90° clockwise - k1-pro displays images rotated 90° CCW
        img = img.transpose(Image.Transpose.ROTATE_270)

        # Convert to JPEG bytes
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=90, optimize=False,
                 progressive=False, subsampling=2)
        return buffer.getvalue()

    def refresh_images(self):
        """Re-send all cached button images (for after button press)."""
        if not self.connected:
            return
        with self._control_lock:
            device = self._open_control()
            try:
                for button_index, jpeg_data in list(self._button_images.items()):
                    button_id = self._map_button_for_image(button_index)
                    self._send_jpeg_to_button(device, button_id, jpeg_data)
            finally:
                device.close()

    def send_keepalive(self):
        """Send CONNECT command to maintain stream deck mode."""
        if not self.connected:
            return
        with self._control_lock:
            device = self._open_control()
            try:
                self._write_report(device, CONNECT_COMMAND)
            finally:
                device.close()

    def start_keepalive(self):
        """Start background thread that continuously sends images.

        VSD Craft continuously sends images at ~25fps to keep the device in
        stream deck mode, plus CONNECT heartbeat every 10s.
        """
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return

        self._keepalive_stop.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True
        )
        self._keepalive_thread.start()

    def stop_keepalive(self):
        """Stop the keepalive thread."""
        self._keepalive_stop.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=2)

    def _keepalive_loop(self):
        """Background loop: continuously send images + periodic CONNECT."""
        last_connect = time.time()
        while not self._keepalive_stop.is_set():
            if self.connected and self._button_images:
                try:
                    # Cycle through all cached button images
                    with self._control_lock:
                        device = self._open_control()
                        try:
                            for button_index, jpeg_data in list(self._button_images.items()):
                                if self._keepalive_stop.is_set():
                                    break
                                button_id = self._map_button_for_image(button_index)
                                self._send_jpeg_to_button(device, button_id, jpeg_data)

                            # Send CONNECT heartbeat every 10s
                            if time.time() - last_connect >= CONNECT_INTERVAL:
                                self._write_report(device, CONNECT_COMMAND)
                                last_connect = time.time()
                        finally:
                            device.close()
                except Exception:
                    pass  # Don't crash keepalive on transient errors

            self._keepalive_stop.wait(KEEPALIVE_INTERVAL)

    def close(self):
        """Close the device connection."""
        self.stop_keepalive()
        self.connected = False
        print("Device closed")


def main():
    """Test the k1-pro connection"""
    print("=" * 55)
    print("  vsdinside k1-pro Test")
    print("=" * 55 + "\n")

    deck = K1Pro()
    deck.connect()

    # Test: Set images on all 6 buttons
    colors = ["#FF0066", "#00AAFF", "#FF4400", "#FFAA00", "#FF0000", "#00FF00"]
    for i in range(6):
        image = K1Pro.create_button_image(f"B{i+1}", f"{i+1}", colors[i])
        deck.set_button_image(i, image)
        print(f"  Button {i+1} set")

    # Open event device BEFORE starting keepalive (avoids HID conflict)
    event_dev = deck._open_events()
    event_dev.set_nonblocking(1)

    # Start keepalive to prevent device from dropping out of stream deck mode
    deck.start_keepalive()
    print("  Keepalive started (continuous image refresh at 20fps)")

    print("\nPress buttons/knobs ONE AT A TIME, slowly.")
    print("Press B1, wait, B2, wait, ... B6")
    print("Then K1 turn, K2 turn, K3 turn, K1 press, K2 press, K3 press")
    print("(Ctrl+C to exit)\n")

    try:
        event_num = 0
        while True:
            data = event_dev.read(WRITE_SIZE, 100)
            if not data or len(data) < 2:
                continue

            report_id = data[0]
            event_num += 1

            if report_id == 0x04:
                # Report ID 4: Button/knob events (after proper init)
                # Format: ACK\x00\x00OK\x00\x00 + ID(byte 10) + STATE(byte 11)
                control_id = data[10]
                state = data[11]

                # Map protocol ID to physical button
                if control_id in BUTTON_ID_MAP:
                    phys_idx = BUTTON_ID_MAP.index(control_id)
                    if state == 1:
                        print(f"  #{event_num:3d}  BUTTON   B{phys_idx+1} PRESSED")
                    elif state == 0:
                        print(f"  #{event_num:3d}  BUTTON   B{phys_idx+1} RELEASED")
                # Knob turn events
                elif control_id == 0x51:
                    print(f"  #{event_num:3d}  KNOB     K1 TURN CLOCKWISE")
                elif control_id == 0x50:
                    print(f"  #{event_num:3d}  KNOB     K1 TURN COUNTER-CW")
                elif control_id == 0x61:
                    print(f"  #{event_num:3d}  KNOB     K2 TURN CLOCKWISE")
                elif control_id == 0x60:
                    print(f"  #{event_num:3d}  KNOB     K2 TURN COUNTER-CW")
                elif control_id == 0x91:
                    print(f"  #{event_num:3d}  KNOB     K3 TURN CLOCKWISE")
                elif control_id == 0x90:
                    print(f"  #{event_num:3d}  KNOB     K3 TURN COUNTER-CW")
                # Knob press events
                elif control_id == 0x25:
                    print(f"  #{event_num:3d}  KNOB     K1 PRESSED")
                elif control_id == 0x30:
                    print(f"  #{event_num:3d}  KNOB     K2 PRESSED")
                elif control_id == 0x31:
                    print(f"  #{event_num:3d}  KNOB     K3 PRESSED")
                else:
                    # Unknown control
                    raw_hex = ' '.join(f'{b:02x}' for b in data[:24])
                    print(f"  #{event_num:3d}  UNKNOWN  id=0x{control_id:02x} state={state}  raw=[{raw_hex}]")

            elif report_id == 0x01:
                # Report ID 1: button press/release
                key_id = data[1]
                raw_hex = ' '.join(f'{b:02x}' for b in data[:6])
                if key_id == 0:
                    print(f"  #{event_num:3d}  RELEASE                raw=[{raw_hex}]")
                    # Device reverts to keyboard mode on press; re-send images
                    try:
                        deck.refresh_images()
                    except Exception as e:
                        print(f"       refresh failed: {e}")
                else:
                    print(f"  #{event_num:3d}  PRESS   id=0x{key_id:02x} ({key_id:3d})  raw=[{raw_hex}]")

            else:
                raw_hex = ' '.join(f'{b:02x}' for b in data[:24])
                print(f"  #{event_num:3d}  RPT{report_id}    raw=[{raw_hex}]")
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        event_dev.close()
        deck.close()


if __name__ == "__main__":
    main()
