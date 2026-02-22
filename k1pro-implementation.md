# k1-pro Implementation Guide - FINAL

## Quick Reference

### macOS Close/Reopen Pattern (CRITICAL)
```python
# Event loop pattern for macOS
event_dev = deck._open_events()
while True:
    data = event_dev.read(1024, 100)
    if needs_update:
        event_dev.close()                    # 1. Close event device
        deck.set_button_image(idx, img)      # 2. Update button
        event_dev.open_path(deck._event_path) # 3. Reopen event device
```

### Basic Usage
```python
# Initialize
deck = K1Pro()
deck.connect()

# Set button image (0-5)
image = K1Pro.create_button_image("Hello", "World", "#FF0066")
deck.set_button_image(0, image)

# Read events
event_dev = deck._open_events()
event_dev.set_nonblocking(1)
data = event_dev.read(1024, 100)
if data and data[0] == 0x04:
    control_id = data[10]  # Button/knob ID
    state = data[11]        # 1=pressed, 0=released
```

### Event IDs Quick Lookup
```python
# Buttons: B1=5, B2=3, B3=1, B4=6, B5=4, B6=2
# Knob 1: CW=0x51, CCW=0x50, Press=0x25
# Knob 2: CW=0x61, CCW=0x60, Press=0x30
# Knob 3: CW=0x91, CCW=0x90, Press=0x31
```

---

## Device Information

**Device:** vsdinside k1-pro
**Vendor ID:** 0x5548
**Product ID:** 0x1025
**Manufacturer:** HOTSPOTEKUSB

**Physical Layout:**
```
┌────────────────────────────┐
│  🎛️ K1   🎛️ K2   🎛️ K3     │  Knobs (top row)
├────┬────┬────┬────┬────┬───┤
│ B1 │ B2 │ B3 │ B4 │ B5 │ B6│  Buttons (6 LCD buttons, 64x64px each)
└────┴────┴────┴────┴────┴───┘
```

## Protocol Specification

### Mode: Stream Deck (VSD Craft Compatible)

**Key Parameters:**
- **Report ID:** 4 (0x04)
- **Write Size:** 1024 bytes (Report ID + 1023 data)
- **Data Size:** 1023 bytes per packet
- **Image Size:** 64x64 pixels
- **Image Format:** JPEG (quality 90%, no progressive, subsampling=2)
- **Image Rotation:** 90° clockwise before sending (device displays rotated 90° CCW)

### Initialization Sequence

VSD Craft sends this exact sequence on startup (from USB capture analysis):

```python
# VSD Craft init sequence (NOT the same as Fifine D6!)
DIS_COMMAND    = b'\x43\x52\x54\x00\x00\x44\x49\x53\x00\x00'               # CRT+DIS
WAKE_COMMAND   = b'\x43\x52\x54\x00\x00\x77\x61\x6b\x65\x00'              # CRT+wake
LIG_COMMAND    = b'\x43\x52\x54\x00\x00\x4c\x49\x47\x00\x00\x00\x19'       # CRT+LIG
QUCMD_COMMAND  = b'\x43\x52\x54\x00\x00\x51\x55\x43\x4d\x44\x11\x11\x00\x11\x00\x11'  # CRT+QUCMD
CPOS_COMMAND   = b'\x43\x52\x54\x00\x00\x43\x50\x4f\x53\x00\x4d'          # CRT+CPOS M
# LIG_COMMAND (second time)
CLE_COMMAND    = b'\x43\x52\x54\x00\x00\x43\x4c\x45\x00\x00\x00\xff'      # CRT+CLE
STP_COMMAND    = b'\x43\x52\x54\x00\x00\x53\x54\x50\x00\x00'              # CRT+STP
```

**Timing between commands:** 1-2ms, with longer delays (2ms) after CPOS and STP.

### BAT Command (Button Image Transfer)

Same structure as Fifine D6, different parameters:

```
BAT Header (13 bytes):
  Bytes 0-2:   CRT (0x43 0x52 0x54)
  Bytes 3-4:   \x00\x00 (padding)
  Bytes 5-7:   BAT (0x42 0x41 0x54)
  Bytes 8-9:   \x00\x00 (padding)
  Byte 10:     Size high byte (big-endian)
  Byte 11:     Size low byte (big-endian)
  Byte 12:     Button ID (1-based: 1,2,3,4,5,6)

JPEG Data Packets:
  - Sent in chunks of up to 1023 bytes
  - Each packet prepended with Report ID 0x04
  - Padded to 1024 bytes total

STP Terminator:
  - CRT\x00\x00STP\x00\x00 command signals end of transfer
```

### Button ID Mapping

**Physical to Protocol mapping:**
```
Physical Layout:    [B1][B2][B3][B4][B5][B6]
Protocol IDs:       [ 5][ 3][ 1][ 6][ 4][ 2]

BUTTON_ID_MAP = [5, 3, 1, 6, 4, 2]  # Index = physical button (0-5)
```

### Event Format

After proper initialization, events come via HID input reports (Report ID 4):

```
Event Structure:
  Byte 0:      Report ID (0x04)
  Bytes 1-9:   ACK\x00\x00OK\x00\x00 (header)
  Byte 10:     Control ID (button/knob identifier)
  Byte 11:     State (0x01 = pressed, 0x00 = released for buttons)
  Bytes 12+:   Padding (zeros)
```

**Button Events:**
```
B1: ID = 0x05 (5)   - Button 1
B2: ID = 0x03 (3)   - Button 2
B3: ID = 0x01 (1)   - Button 3
B4: ID = 0x06 (6)   - Button 4
B5: ID = 0x04 (4)   - Button 5
B6: ID = 0x02 (2)   - Button 6

State: 0x01 = pressed, 0x00 = released
```

**Knob Turn Events:**
```
K1 Clockwise:        0x51 (81)
K1 Counter-CW:       0x50 (80)
K2 Clockwise:        0x61 (97)
K2 Counter-CW:       0x60 (96)
K3 Clockwise:        0x91 (145)
K3 Counter-CW:       0x90 (144)

State: Always 0x00
```

**Knob Press Events:**
```
K1 Press: 0x25 (37)
K2 Press: 0x30 (48)
K3 Press: 0x31 (49)

State: 0x01 when pressed (no release event detected)
```

### Keepalive Mechanism

**CRITICAL:** The device requires continuous communication to stay in stream deck mode.

VSD Craft's keepalive strategy:
1. **Continuous image refresh:** Send all button images in rotation at ~25fps (every 40ms)
2. **Periodic CONNECT heartbeat:** Send CONNECT command every 10 seconds

```python
CONNECT_COMMAND = b'\x43\x52\x54\x00\x00\x43\x4f\x4e\x4e\x45\x43\x54'

# Keepalive implementation:
# - Send all cached button images every 50ms (20fps) in background thread
# - Send CONNECT command every 10 seconds
# - Without this, device reverts to keyboard mode on button press
```

## Python Implementation (k1pro_python.py)

### Complete Working Code Structure

```python
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
WRITE_SIZE = 1024
DATA_SIZE = 1023
IMAGE_SIZE = (64, 64)  # 64x64 JPEG images

# Timing
TIMING_BAT_HEADER = 0.01
TIMING_JPEG_CHUNK = 0.01
TIMING_STP_CMD = 0.01
TIMING_CONNECT = 0.05
KEEPALIVE_INTERVAL = 0.05  # 20fps
CONNECT_INTERVAL = 10.0

# Button mapping
BUTTON_ID_MAP = [5, 3, 1, 6, 4, 2]

# Knob IDs
KNOB1_CW, KNOB1_CCW = 0x51, 0x50
KNOB2_CW, KNOB2_CCW = 0x61, 0x60
KNOB3_CW, KNOB3_CCW = 0x91, 0x90
KNOB1_PRESS, KNOB2_PRESS, KNOB3_PRESS = 0x25, 0x30, 0x31
```

### Key Methods

```python
def send_init(self):
    """VSD Craft init sequence"""
    device = self._open_control()
    try:
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

def create_button_image(label, sublabel=None, bg_color="#000000"):
    """Create 64x64 JPEG, rotated 90° CW"""
    img = Image.new('RGB', IMAGE_SIZE, bg_color)
    draw = ImageDraw.Draw(img)

    # Draw text (centered)
    # ... (text drawing code)

    # Rotate 90° clockwise
    img = img.transpose(Image.Transpose.ROTATE_270)

    # Convert to JPEG
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90,
             optimize=False, progressive=False, subsampling=2)
    return buffer.getvalue()

def start_keepalive(self):
    """Background thread: continuous images + periodic CONNECT"""
    # Send all button images every 50ms
    # Send CONNECT every 10s
```

## Comparison: k1-pro vs Fifine D6

| Feature | k1-pro | Fifine D6 |
|---------|--------|-----------|
| **Report ID** | 4 | 2 |
| **Packet Size** | 1024 bytes | 512 bytes |
| **Data Size** | 1023 bytes | 480 bytes |
| **Image Size** | 64×64 px | 100×100 px |
| **Image Rotation** | 90° CW | 180° |
| **Protocol** | CRT+BAT ✓ | CRT+BAT ✓ |
| **Init Sequence** | DIS/wake/LIG/QUCMD/CPOS/LIG/CLE/STP | DIS/LIG/QUCMD/LIG/CLE |
| **Button Count** | 6 buttons | 15 buttons |
| **Extra Features** | 3 knobs (turn + press) | None |
| **Keepalive** | Continuous images + CONNECT | Continuous images only |

## USB Capture Analysis

### Captures Analyzed
1. **vsd-k1-pro.pcapng** - Initial capture (mid-session, missing init)
2. **vsd-k1-pro_scene_switch_button_presses.pcapng** - Complete session with init

### Key Findings from Captures

**Init Sequence Timing:**
- Frame 4: DIS (t=0.000729s)
- Frame 6: wake (t=0.001978s, Δ=1.25ms)
- Frame 12: LIG (t=0.002601s, Δ=0.62ms)
- Frame 14: QUCMD (t=0.002722s, Δ=0.12ms)
- Frame 16: CPOS M (t=0.002847s, Δ=0.13ms)
- Frame 18: LIG (t=0.004476s, Δ=1.63ms)
- Frame 20: CLE (t=0.005478s, Δ=1.00ms)
- Frame 22: STP (t=0.006110s, Δ=0.63ms)
- Frame 24: First BAT (t=0.008109s, Δ=2.00ms)

**Keepalive Pattern:**
- CONNECT at t=10.001s, t=20.001s (every 10 seconds)
- BAT commands every ~40ms (25fps continuous)

## Tools Created

### Core SDK
1. ✅ **k1pro_python.py** - Complete working HID SDK
   - Device initialization and control
   - Image upload (64×64 JPEG, rotated)
   - Event reading (buttons, knobs)
   - Retry logic for macOS
   - Thread-safe device access

### Testing & Analysis
2. ✅ **test_k1pro.py** - Test suite
3. ✅ **k1pro_button_mapper.py** - Interactive mapping tool
4. ✅ **analyze_button_press_capture.py** - USB capture analyzer

### Interactive Demos
5. ✅ **k1pro_counter_test.py** - Basic counter demo
   - Single-threaded, close/reopen pattern
   - 3 knobs control 3 counters
   - Demonstrates reliable macOS HID handling

6. ✅ **k1pro_knob_demo.py** - Full interactive demo (RECOMMENDED)
   - Per-button updates (optimal performance)
   - K1/K2: Counter controls
   - K3: Rainbow speed control (50-2000ms, ±50ms steps)
   - B3: Speed display in milliseconds
   - B4/B5/B6: Rainbow color cycling
   - Knob press: Pause/resume animation
   - Initial speed: 500ms

7. ✅ **k1pro_knob_demo-entire-screen.py** - Full-screen rendering demo
   - Treats 6 buttons as unified 384×64 canvas
   - Demonstrates full-screen composition
   - Less efficient (educational purposes)

### Pending
8. ⬜ **claude_mode_button_k1pro.py** - Claude integration (planned)

## Success Criteria

### Phase 1: Protocol Reverse Engineering ✅
✅ Protocol fully reverse engineered
✅ USB captures analyzed (2 captures)
✅ Init sequence identified (DIS/wake/LIG/QUCMD/CPOS/LIG/CLE/STP)
✅ Image parameters confirmed (64×64, 90° CW rotation)
✅ Button ID mapping confirmed ([5,3,1,6,4,2])
✅ Knob event IDs mapped (turn CW/CCW, press)
✅ Keepalive mechanism documented (continuous images + CONNECT)
✅ Event format decoded (ACK+OK header)

### Phase 2: Implementation ✅
✅ Python SDK created (k1pro_python.py)
✅ All buttons working (image display + press events)
✅ All knobs working (turn CW/CCW + press events)
✅ macOS HID limitations identified and solved
✅ Close/reopen pattern implemented
✅ Retry logic for device access
✅ Thread-safe device handling

### Phase 3: Demos & Testing ✅
✅ Basic counter demo (k1pro_counter_test.py)
✅ Interactive demo with rainbow animation (k1pro_knob_demo.py)
✅ Full-screen rendering demo (k1pro_knob_demo-entire-screen.py)
✅ Performance optimization documented
✅ Best practices established

### Phase 4: Documentation ✅
✅ Complete protocol specification
✅ macOS implementation patterns documented
✅ Troubleshooting guide
✅ Performance comparison (per-button vs full-screen)
✅ Working code examples

### Phase 5: Integration (Pending)
⬜ Claude Code integration
⬜ Production deployment
⬜ User testing

## Troubleshooting

### Device Reverts to Keyboard Mode
**Cause:** Insufficient keepalive communication
**Solution:**
- Ensure continuous image sending at 20fps minimum
- Send CONNECT heartbeat every 10s
- Both are required!

### Images Don't Display
**Checklist:**
1. ✓ Correct init sequence (DIS/wake/LIG/QUCMD/CPOS/LIG/CLE/STP)
2. ✓ Image size: 64×64 pixels
3. ✓ Image rotation: 90° clockwise
4. ✓ Report ID: 0x04
5. ✓ Packet size: 1024 bytes (1 + 1023)
6. ✓ BAT header format correct
7. ✓ Button ID from BUTTON_ID_MAP

### Button Events Not Received
- Check event endpoint (usage 0x0002)
- Parse byte 10 for control ID
- Parse byte 11 for state
- Events have ACK\x00\x00OK\x00\x00 header

### macOS Specific Issues
- **Karabiner-Elements:** Must be quit (blocks HID)
- **VSD Craft:** Must be quit (exclusive access)
- **Input Monitoring:** Grant permission to terminal/IDE
- **USB Hub:** Use direct connection only

## macOS HID Implementation Patterns

### Critical Limitation: Single Endpoint Access

**Problem:** macOS HID driver does **NOT allow simultaneous access** to multiple endpoints on the same device.

```
Device has 2 HID endpoints:
├─ Control endpoint (usage 0x0001) - for sending commands/images
└─ Event endpoint (usage 0x0002) - for reading button/knob events

CANNOT have both open at the same time on macOS! ❌
```

### Solution: Close/Reopen Pattern

**Working Pattern for Interactive Applications:**

```python
# 1. Initialize device
deck.connect()
deck.send_init()

# 2. Set initial button images (control endpoint opens/closes)
deck.set_button_image(0, image)

# 3. Open event device for reading
event_dev = deck._open_events()
event_dev.set_nonblocking(1)

# 4. Event loop
while True:
    # Read events (event device is open)
    data = event_dev.read(1024, 100)

    if knob_turned:
        # Close event device FIRST
        event_dev.close()

        # Now we can open control device and update button
        deck.set_button_image(button_index, new_image)
        # (set_button_image opens control, sends, closes)

        # Reopen event device
        event_dev.open_path(deck._event_path)
```

### Retry Logic for Device Opening

macOS may not immediately release HID device after close. Add retry with delays:

```python
def _open_control(self):
    """Open control endpoint with retry logic for macOS."""
    device = hid.device()

    # Retry with delays for macOS HID device release
    max_retries = 5
    for attempt in range(max_retries):
        try:
            device.open_path(self._control_path)
            return device
        except OSError as e:
            if attempt < max_retries - 1:
                time.sleep(0.1)  # Wait 100ms for OS to release
            else:
                raise RuntimeError(f"Failed after {max_retries} attempts")
```

### Threading Considerations

**❌ DON'T:** Use keepalive thread with event device open
- Background thread continuously opens/closes control device
- Main thread keeps event device open
- macOS conflict: both can't access device simultaneously
- Result: `OSError: open failed`

**✅ DO:** Use single-threaded event loop
- No background threads
- Close/reopen event device when updating buttons
- Simple and reliable

```python
# BAD - Threading conflicts on macOS
deck.start_keepalive()  # Background thread
event_dev = deck._open_events()  # Main thread
# Both try to access device → OSError

# GOOD - Single threaded
event_dev = deck._open_events()
while True:
    data = event_dev.read(1024, 100)
    if needs_update:
        event_dev.close()
        deck.set_button_image(...)  # Opens/closes control
        event_dev.open_path(deck._event_path)
```

### Performance Optimization

**Per-Button Updates (Optimal):**
```python
# Only update what changed
if knob1_turned:
    update_button(0, new_value)  # 1 button = 1× 64×64 JPEG

if rainbow_cycling:
    for i in [3, 4, 5]:  # B4, B5, B6
        update_button(i, color)  # 3 buttons = 3× 64×64 JPEGs
```

**Full-Screen Updates (Less Efficient):**
```python
# Always updates all 6 buttons
screen = render_full_screen(...)  # 384×64 canvas
for i in range(6):
    update_button(i, ...)  # 6 buttons = 6× 64×64 JPEGs

# 2-6× more data than needed! ❌
```

**Verdict:** Use **per-button updates** for interactive applications. Full-screen only beneficial for:
- Graphics spanning multiple buttons
- Most updates affect most buttons
- Need atomic synchronized updates

### Working Demos

**✅ k1pro_counter_test.py** - Basic counter demo
- Single-threaded
- Close/reopen pattern
- Knobs control button counters
- Simple and reliable

**✅ k1pro_knob_demo.py** - Interactive demo (RECOMMENDED)
- Single-threaded event loop
- Per-button updates (optimal)
- Features:
  - K1/K2: Counter controls (B1, B2)
  - K3: Rainbow speed control (50-2000ms)
  - B3: Speed display
  - B4/B5/B6: Rainbow animation
  - Knob press: Pause/resume rainbow

**⚠️ k1pro_knob_demo-entire-screen.py** - Full-screen rendering
- Treats 6 buttons as 384×64 canvas
- Always updates all 6 buttons
- Less efficient (2-6× more data)
- Use only if graphics span multiple buttons

### Best Practices Summary

1. **Always close event device before opening control device**
2. **Reopen event device immediately after control operations**
3. **Use single-threaded event loop** (no keepalive thread)
4. **Add retry logic** with delays for device opening
5. **Update only changed buttons** for best performance
6. **Use threading.Lock** if you must use background threads
7. **Test with direct USB connection** (no hubs)

## Next Steps

### Claude Integration Design

**Button Layout (6 buttons):**
```
┌────┬────┬────┐
│ B1 │ B2 │ B3 │  B1: STATUS/MODE indicator
├────┼────┼────┤  B2: COPY (copy command to clipboard)
│ B4 │ B5 │ B6 │  B3: CANCEL (interrupt operation)
└────┴────┴────┘  B4: RETHINK (ask for more info)
                  B5: DENY (reject permission)
                  B6: ALLOW (grant permission)
```

**Knob Usage (3 knobs):**
- K1: Scroll through history
- K2: Adjust verbosity/detail level
- K3: Navigate Claude sessions
- Knob presses: Quick actions (TBD)

## Resources

- **Web Interface:** https://device.vsdinside.com/keyboard
- **VSD Craft:** com.mirabox.streamdock
- **Working Python SDK:** k1pro_python.py
- **USB Captures:** usb-capture/vsd-k1-pro*.pcapng
- **Reference:** Fifine D6 implementation (similar protocol)

## Final Notes

The k1-pro uses a **CRT+BAT protocol** similar to Fifine D6 but with critical differences:
1. Different init sequence (more complex)
2. Smaller images (64×64 vs 100×100)
3. Different rotation (90° CW vs 180°)
4. Additional CONNECT heartbeat required
5. Knob support (turn + press)

The protocol is **fully understood and working** ✅
