#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "hidapi",
#     "pillow",
# ]
# ///
"""
k1-pro Knob Demo - Full Screen Mode

Treats all 6 buttons as one continuous 384×64 pixel screen.
Updates the entire screen at once for smoother visuals.
"""

from k1pro_python import K1Pro, WRITE_SIZE, IMAGE_SIZE
import time
import colorsys
from PIL import Image, ImageDraw, ImageFont
import io


# Screen dimensions: 6 buttons × 64 pixels each
SCREEN_WIDTH = 384  # 6 buttons × 64px
SCREEN_HEIGHT = 64


def hue_to_hex(hue):
    """Convert HSV hue (0-1) to hex color."""
    rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
    r, g, b = int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def render_full_screen(counter1, counter2, speed_ms, rainbow_colors):
    """
    Render the entire 384×64 screen with all button content.

    Layout (before rotation):
    [B1: Counter1] [B2: Counter2] [B3: Speed] [B4: Rainbow] [B5: Rainbow] [B6: Rainbow]
    """
    # Create full screen image
    screen = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), '#000000')
    draw = ImageDraw.Draw(screen)

    # Load fonts
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18, index=1)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12, index=1)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Button configurations
    buttons = [
        {"x": 0,   "bg": "#FF0066", "label": str(counter1), "sublabel": "K1"},
        {"x": 64,  "bg": "#00AAFF", "label": str(counter2), "sublabel": "K2"},
        {"x": 128, "bg": "#FF4400", "label": str(speed_ms), "sublabel": "ms"},
        {"x": 192, "bg": rainbow_colors[0], "label": "B4", "sublabel": "◉"},
        {"x": 256, "bg": rainbow_colors[1], "label": "B5", "sublabel": "◉"},
        {"x": 320, "bg": rainbow_colors[2], "label": "B6", "sublabel": "◉"},
    ]

    # Draw each button section
    for btn in buttons:
        x = btn["x"]

        # Fill background
        draw.rectangle([x, 0, x + 64, 64], fill=hex_to_rgb(btn["bg"]))

        # Draw main label (centered)
        label = btn["label"]
        bbox = draw.textbbox((0, 0), label, font=font_large)
        text_width = bbox[2] - bbox[0]
        label_x = x + (64 - text_width) // 2
        label_y = 15 if btn["sublabel"] else 22
        draw.text((label_x, label_y), label, fill="black", font=font_large)

        # Draw sublabel
        if btn["sublabel"]:
            sublabel = btn["sublabel"]
            bbox = draw.textbbox((0, 0), sublabel, font=font_small)
            sub_width = bbox[2] - bbox[0]
            sub_x = x + (64 - sub_width) // 2
            draw.text((sub_x, 38), sublabel, fill="black", font=font_small)

    return screen


def screen_to_button_images(screen):
    """
    Slice the full screen into 6 button images and rotate each for k1-pro.

    Returns list of (button_index, jpeg_data) tuples.
    """
    button_images = []

    for i in range(6):
        # Extract 64×64 region for this button
        x = i * 64
        button_img = screen.crop((x, 0, x + 64, 64))

        # Rotate 90° counter-clockwise (k1-pro displays images rotated)
        button_img = button_img.transpose(Image.Transpose.ROTATE_270)

        # Convert to JPEG
        buffer = io.BytesIO()
        button_img.save(buffer, format='JPEG', quality=90, optimize=False,
                       progressive=False, subsampling=2)
        jpeg_data = buffer.getvalue()

        button_images.append((i, jpeg_data))

    return button_images


def update_full_screen(deck, event_dev, counter1, counter2, speed_ms, rainbow_colors):
    """Update all 6 buttons with new full-screen render."""
    # Close event device before control operations
    event_dev.close()

    # Render full screen
    screen = render_full_screen(counter1, counter2, speed_ms, rainbow_colors)

    # Slice into button images
    button_images = screen_to_button_images(screen)

    # Send all buttons
    for button_idx, jpeg_data in button_images:
        deck._button_images[button_idx] = jpeg_data
        button_id = deck._map_button_for_image(button_idx)
        device = deck._open_control()
        try:
            deck._send_jpeg_to_button(device, button_id, jpeg_data)
        finally:
            device.close()

    # Reopen event device
    event_dev.open_path(deck._event_path)


def main():
    print("=" * 60)
    print("  k1-pro Knob Demo - Full Screen Mode")
    print("=" * 60)
    print()
    print("Controls:")
    print("  Turn K1/K2: Adjust numbers on B1/B2")
    print("  Turn K3: Adjust rainbow speed (B3 shows speed in ms)")
    print("  Press K1/K2/K3: Pause/resume rainbow on B4/B5/B6")
    print("  Ctrl+C: Exit")
    print()

    deck = K1Pro()
    deck.connect()

    # State
    counter1 = 0
    counter2 = 0
    rainbow_speed_ms = 500
    color_hue = 0.0
    color_cycling = False
    last_color_update = time.time()

    # Initial rainbow colors
    rainbow_colors = [
        hue_to_hex(0.0),
        hue_to_hex(0.33),
        hue_to_hex(0.67)
    ]

    # Render and display initial screen
    update_full_screen(deck, deck._open_events(), counter1, counter2, rainbow_speed_ms, rainbow_colors)

    # Open event device
    event_dev = deck._open_events()
    event_dev.set_nonblocking(1)

    print("✓ Full screen demo started")
    print("Waiting for knob events...\n")

    try:
        while True:
            now = time.time()

            # Update rainbow colors if cycling
            speed_seconds = rainbow_speed_ms / 1000.0
            if color_cycling and now - last_color_update >= speed_seconds:
                color_hue = (color_hue + 0.05) % 1.0

                # Update rainbow colors
                rainbow_colors = [
                    hue_to_hex((color_hue + 0.0) % 1.0),
                    hue_to_hex((color_hue + 0.33) % 1.0),
                    hue_to_hex((color_hue + 0.67) % 1.0)
                ]

                # Re-render entire screen
                update_full_screen(deck, event_dev, counter1, counter2, rainbow_speed_ms, rainbow_colors)
                last_color_update = now

            # Read events
            data = event_dev.read(WRITE_SIZE, 10)
            if data and len(data) >= 11:
                report_id = data[0]
                if report_id == 0x04:
                    control_id = data[10]
                    needs_update = False

                    # Knob 1 - Counter 1
                    if control_id == 0x51:  # K1 CW
                        counter1 += 1
                        needs_update = True
                        print(f"K1 ↑  B1 = {counter1}")
                    elif control_id == 0x50:  # K1 CCW
                        counter1 -= 1
                        needs_update = True
                        print(f"K1 ↓  B1 = {counter1}")

                    # Knob 2 - Counter 2
                    elif control_id == 0x61:  # K2 CW
                        counter2 += 1
                        needs_update = True
                        print(f"K2 ↑  B2 = {counter2}")
                    elif control_id == 0x60:  # K2 CCW
                        counter2 -= 1
                        needs_update = True
                        print(f"K2 ↓  B2 = {counter2}")

                    # Knob 3 - Speed control
                    elif control_id == 0x91:  # K3 CW - faster
                        rainbow_speed_ms = max(50, rainbow_speed_ms - 50)
                        needs_update = True
                        print(f"K3 ↑  Speed = {rainbow_speed_ms}ms (faster)")
                    elif control_id == 0x90:  # K3 CCW - slower
                        rainbow_speed_ms = min(2000, rainbow_speed_ms + 50)
                        needs_update = True
                        print(f"K3 ↓  Speed = {rainbow_speed_ms}ms (slower)")

                    # Knob press - toggle cycling
                    elif control_id in [0x25, 0x30, 0x31]:
                        color_cycling = not color_cycling
                        knob_num = {0x25: 1, 0x30: 2, 0x31: 3}[control_id]
                        status = "RESUMED" if color_cycling else "PAUSED"
                        print(f"K{knob_num} pressed → Rainbow cycling {status}")

                    # Update full screen if needed
                    if needs_update:
                        update_full_screen(deck, event_dev, counter1, counter2, rainbow_speed_ms, rainbow_colors)

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        event_dev.close()
        deck.close()


if __name__ == "__main__":
    main()
