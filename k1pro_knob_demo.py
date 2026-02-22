#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "hidapi",
#     "pillow",
# ]
# ///
"""
k1-pro Knob Demo

- Turn K1/K2/K3 to increase/decrease numbers on B1/B2/B3
- Background colors cycle through palette automatically
- Press any knob to pause/resume color cycling
"""

from k1pro_python import K1Pro, WRITE_SIZE
import time
import colorsys


def hue_to_hex(hue):
    """Convert HSV hue (0-1) to hex color."""
    rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
    r, g, b = int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def update_button(deck, event_dev, button_idx, value, color):
    """Update a single button image (with event device close/reopen for macOS)."""
    image = K1Pro.create_button_image(
        label=str(value),
        sublabel=f"K{button_idx+1}",
        bg_color=color
    )

    # Close event device before opening control device (macOS HID limitation)
    event_dev.close()

    # Send to device
    deck.set_button_image(button_idx, image)

    # Reopen event device
    event_dev.open_path(deck._event_path)


def main():
    print("=" * 60)
    print("  k1-pro Knob Demo")
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
    button_values = [0, 0]  # B1, B2 values (B3 shows speed)
    rainbow_speed_ms = 500  # Initial speed: 500ms
    button_colors = ["#FF0066", "#00AAFF", "#FF4400"]  # Fixed colors for B1, B2, B3
    rainbow_colors = ["#FF0000", "#00FF00", "#0000FF"]  # Rainbow colors for B4, B5, B6
    color_hue = 0.0
    color_cycling = False  # Start with cycling OFF to avoid freezing
    last_color_update = time.time()

    # Set initial rainbow images on B4, B5, B6
    for i in range(3, 6):
        rainbow_idx = i - 3
        offset = [0.0, 0.33, 0.67][rainbow_idx]
        rainbow_colors[rainbow_idx] = hue_to_hex((color_hue + offset) % 1.0)
        image = K1Pro.create_button_image(
            label=f"B{i+1}",
            sublabel="◉",
            bg_color=rainbow_colors[rainbow_idx]
        )
        deck.set_button_image(i, image)

    # Set initial images on B1, B2 with counters
    initial_colors = ["#FF0066", "#00AAFF"]  # Pink, Blue
    for i in range(2):
        image = K1Pro.create_button_image(
            label=str(button_values[i]),
            sublabel=f"K{i+1}",
            bg_color=initial_colors[i]
        )
        deck.set_button_image(i, image)

    # Set B3 to show speed
    image = K1Pro.create_button_image(
        label=f"{rainbow_speed_ms}",
        sublabel="ms",
        bg_color="#FF4400"
    )
    deck.set_button_image(2, image)

    # Open event device
    event_dev = deck._open_events()
    event_dev.set_nonblocking(1)

    print("✓ Demo started")
    print("Waiting for knob events...\n")

    try:
        while True:
            now = time.time()

            # Update colors based on rainbow_speed_ms if cycling (B4, B5, B6)
            speed_seconds = rainbow_speed_ms / 1000.0
            if color_cycling and now - last_color_update >= speed_seconds:
                color_hue = (color_hue + 0.05) % 1.0

                # Close event device to update B4, B5, B6
                event_dev.close()

                # Update B4, B5, B6 with new rainbow colors
                for i in range(3):
                    button_idx = i + 3  # B4, B5, B6 (indices 3, 4, 5)
                    offset = [0.0, 0.33, 0.67][i]
                    rainbow_colors[i] = hue_to_hex((color_hue + offset) % 1.0)
                    image = K1Pro.create_button_image(
                        label=f"B{button_idx+1}",
                        sublabel="◉",
                        bg_color=rainbow_colors[i]
                    )
                    deck.set_button_image(button_idx, image)

                # Reopen event device
                event_dev.open_path(deck._event_path)

                last_color_update = now

            # Read events (non-blocking)
            data = event_dev.read(WRITE_SIZE, 10)
            if data and len(data) >= 11:
                report_id = data[0]
                if report_id == 0x04:
                    control_id = data[10]

                    # Knob 1
                    if control_id == 0x51:  # K1 CW
                        button_values[0] += 1
                        update_button(deck, event_dev, 0, button_values[0], button_colors[0])
                        print(f"K1 ↑  B1 = {button_values[0]}")
                    elif control_id == 0x50:  # K1 CCW
                        button_values[0] -= 1
                        update_button(deck, event_dev, 0, button_values[0], button_colors[0])
                        print(f"K1 ↓  B1 = {button_values[0]}")

                    # Knob 2
                    elif control_id == 0x61:  # K2 CW
                        button_values[1] += 1
                        update_button(deck, event_dev, 1, button_values[1], button_colors[1])
                        print(f"K2 ↑  B2 = {button_values[1]}")
                    elif control_id == 0x60:  # K2 CCW
                        button_values[1] -= 1
                        update_button(deck, event_dev, 1, button_values[1], button_colors[1])
                        print(f"K2 ↓  B2 = {button_values[1]}")

                    # Knob 3 - Adjust rainbow speed
                    elif control_id == 0x91:  # K3 CW - faster (decrease interval)
                        rainbow_speed_ms = max(50, rainbow_speed_ms - 50)
                        event_dev.close()
                        image = K1Pro.create_button_image(
                            label=f"{rainbow_speed_ms}",
                            sublabel="ms",
                            bg_color="#FF4400"
                        )
                        deck.set_button_image(2, image)
                        event_dev.open_path(deck._event_path)
                        print(f"K3 ↑  Speed = {rainbow_speed_ms}ms (faster)")
                    elif control_id == 0x90:  # K3 CCW - slower (increase interval)
                        rainbow_speed_ms = min(2000, rainbow_speed_ms + 50)
                        event_dev.close()
                        image = K1Pro.create_button_image(
                            label=f"{rainbow_speed_ms}",
                            sublabel="ms",
                            bg_color="#FF4400"
                        )
                        deck.set_button_image(2, image)
                        event_dev.open_path(deck._event_path)
                        print(f"K3 ↓  Speed = {rainbow_speed_ms}ms (slower)")

                    # Knob press
                    elif control_id in [0x25, 0x30, 0x31]:
                        color_cycling = not color_cycling
                        knob_num = {0x25: 1, 0x30: 2, 0x31: 3}[control_id]
                        status = "RESUMED" if color_cycling else "PAUSED"
                        print(f"K{knob_num} pressed → Color cycling {status}")

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        event_dev.close()
        deck.close()


if __name__ == "__main__":
    main()
