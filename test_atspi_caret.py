#!/usr/bin/env python3
"""
Test AT-SPI to get text caret position
This could potentially work across all Wayland compositors
"""

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi
import time

def get_focused_text_caret():
    """Try to get the position of the text caret in the focused application"""
    try:
        # Get the desktop (root of accessibility tree)
        desktop = Atspi.get_desktop(0)

        print(f"Desktop has {desktop.get_child_count()} applications")

        # Find the focused application
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            app_name = app.get_name()

            # Check if this app has focus
            state_set = app.get_state_set()
            if state_set.contains(Atspi.StateType.ACTIVE):
                print(f"✓ Found active app: {app_name}")

                # Try to find the focused text element
                focused = find_focused_text(app)
                if focused:
                    return get_caret_info(focused)
            else:
                print(f"  - {app_name} (not active)")

        print("⚠️  No focused text element found")
        return None

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def find_focused_text(accessible):
    """Recursively search for focused text element"""
    try:
        state_set = accessible.get_state_set()

        # Check if this element is focused and editable
        if state_set.contains(Atspi.StateType.FOCUSED):
            # Try to get text interface
            try:
                text = accessible.get_text_iface()
                if text:
                    print(f"  ✓ Found focused text element: {accessible.get_role_name()}")
                    return accessible
            except:
                pass

        # Recurse through children
        for i in range(accessible.get_child_count()):
            child = accessible.get_child_at_index(i)
            result = find_focused_text(child)
            if result:
                return result

    except:
        pass

    return None

def get_caret_info(accessible):
    """Get caret position and coordinates from text element"""
    try:
        text = accessible.get_text_iface()
        if not text:
            return None

        # Get caret offset (position in text)
        caret_offset = text.get_caret_offset()
        print(f"  Caret offset in text: {caret_offset}")

        # Get character extents at caret position
        # Try different coordinate types
        for coord_type_name, coord_type in [
            ("SCREEN", Atspi.CoordType.SCREEN),
            ("WINDOW", Atspi.CoordType.WINDOW),
        ]:
            try:
                rect = text.get_character_extents(caret_offset, coord_type)
                print(f"  Caret position ({coord_type_name}): x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}")

                if coord_type == Atspi.CoordType.SCREEN:
                    return {
                        'x': rect.x,
                        'y': rect.y,
                        'width': rect.width,
                        'height': rect.height,
                        'offset': caret_offset
                    }
            except Exception as e:
                print(f"  ⚠️  Failed to get {coord_type_name} coords: {e}")

        return None

    except Exception as e:
        print(f"  ❌ Error getting caret info: {e}")
        return None

def main():
    print("AT-SPI Caret Position Test")
    print("=" * 60)
    print("Click into a text field and start typing...")
    print("This script will try to detect the caret position.")
    print("Press Ctrl+C to exit")
    print("=" * 60)

    try:
        # Initialize AT-SPI
        Atspi.init()

        while True:
            print("\n--- Checking for focused text element ---")
            caret_info = get_focused_text_caret()

            if caret_info:
                print(f"\n✅ SUCCESS! Caret found at screen position:")
                print(f"   X: {caret_info['x']}")
                print(f"   Y: {caret_info['y']}")
                print(f"   Size: {caret_info['width']}x{caret_info['height']}")
            else:
                print("\n❌ Could not find caret position")

            # Wait before checking again
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
