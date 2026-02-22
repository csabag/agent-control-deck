#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "hidapi",
#     "pillow",
# ]
# ///
"""
k1pro Counter Test - Turn knobs to increase/decrease button counters

Knob 1 controls Button 1
Knob 2 controls Button 2
Knob 3 controls Button 3

Turn clockwise to increment, counter-clockwise to decrement.
"""

import sys
import time
from k1pro_python import K1Pro, WRITE_SIZE


def update_button_display(deck, event_dev, button_index, counter_value):
    """Update button display with current counter value."""
    # Use different colors for each button
    colors = ["#FF0066", "#00AAFF", "#FF4400"]
    color = colors[button_index] if button_index < len(colors) else "#888888"

    image = K1Pro.create_button_image(
        label=str(counter_value),
        sublabel=f"K{button_index + 1}",
        bg_color=color
    )

    # Close event device before opening control device (macOS HID limitation)
    event_dev.close()

    # Send to device (this also updates the cache)
    deck.set_button_image(button_index, image)

    # Reopen event device
    event_dev.open_path(deck._event_path)


def main():
    print("=" * 55)
    print("  k1-pro Counter Test")
    print("=" * 55)
    print("\nTurn knobs to change counters:")
    print("  Knob 1 → Button 1")
    print("  Knob 2 → Button 2")
    print("  Knob 3 → Button 3")
    print("\nClockwise = increment, Counter-clockwise = decrement")
    print("(Ctrl+C to exit)\n")

    # Initialize device
    deck = K1Pro()
    deck.connect()

    # Initialize counters for buttons 1, 2, 3
    counters = [0, 0, 0]

    # Display initial counter values
    for i in range(3):
        colors = ["#FF0066", "#00AAFF", "#FF4400"]
        image = K1Pro.create_button_image(
            label=str(counters[i]),
            sublabel=f"K{i + 1}",
            bg_color=colors[i]
        )
        deck.set_button_image(i, image)
        print(f"  Button {i + 1} initialized: {counters[i]}")

    # Open event device
    event_dev = deck._open_events()
    event_dev.set_nonblocking(1)

    print("\n  Ready! Turn knobs to change counters.\n")

    try:
        event_num = 0
        while True:
            data = event_dev.read(WRITE_SIZE, 100)
            if not data or len(data) < 2:
                continue

            report_id = data[0]

            if report_id == 0x04:
                # Button/knob events
                control_id = data[10]
                state = data[11]
                event_num += 1

                # Knob 1 events (controls Button 1 / index 0)
                if control_id == 0x51:  # K1 clockwise
                    counters[0] += 1
                    update_button_display(deck, event_dev, 0, counters[0])
                    print(f"  #{event_num:3d}  K1 ↻   Button 1 = {counters[0]}")
                elif control_id == 0x50:  # K1 counter-clockwise
                    counters[0] -= 1
                    update_button_display(deck, event_dev, 0, counters[0])
                    print(f"  #{event_num:3d}  K1 ↺   Button 1 = {counters[0]}")

                # Knob 2 events (controls Button 2 / index 1)
                elif control_id == 0x61:  # K2 clockwise
                    counters[1] += 1
                    update_button_display(deck, event_dev, 1, counters[1])
                    print(f"  #{event_num:3d}  K2 ↻   Button 2 = {counters[1]}")
                elif control_id == 0x60:  # K2 counter-clockwise
                    counters[1] -= 1
                    update_button_display(deck, event_dev, 1, counters[1])
                    print(f"  #{event_num:3d}  K2 ↺   Button 2 = {counters[1]}")

                # Knob 3 events (controls Button 3 / index 2)
                elif control_id == 0x91:  # K3 clockwise
                    counters[2] += 1
                    update_button_display(deck, event_dev, 2, counters[2])
                    print(f"  #{event_num:3d}  K3 ↻   Button 3 = {counters[2]}")
                elif control_id == 0x90:  # K3 counter-clockwise
                    counters[2] -= 1
                    update_button_display(deck, event_dev, 2, counters[2])
                    print(f"  #{event_num:3d}  K3 ↺   Button 3 = {counters[2]}")

            elif report_id == 0x01:
                # Device may revert to keyboard mode on button press
                # Refresh images to get back to stream deck mode
                key_id = data[1]
                if key_id == 0:  # Release event
                    try:
                        deck.refresh_images()
                    except Exception:
                        pass

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        event_dev.close()
        deck.close()


if __name__ == "__main__":
    main()
