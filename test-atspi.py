#!/usr/bin/env python3
"""
Test script for AT-SPI integration.

Run this script and switch focus to different applications to see
what AT-SPI can detect about them.

Usage:
    PYTHONPATH=./src python3 test-atspi.py

    Then click on different applications (VS Code, Firefox, gedit, terminal, etc.)
    and press Enter in the terminal to see what AT-SPI detects.
"""

import sys
import os
import logging

# Enable debug logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from talktype.atspi_helper import (
    is_atspi_available,
    get_focused_context,
    should_use_atspi,
    get_diagnostic_info,
    insert_text_atspi
)

def main():
    print("=" * 70)
    print("TalkType AT-SPI Test Script")
    print("=" * 70)
    print()

    # Check if AT-SPI is available
    if not is_atspi_available():
        print("❌ AT-SPI is NOT available on this system!")
        print("\nThis usually means the python3-pyatspi package is not installed.")
        print("Install it with:")
        print("  Fedora/Nobara: sudo dnf install python3-pyatspi")
        print("  Ubuntu/Debian: sudo apt install python3-pyatspi")
        sys.exit(1)

    print("✅ AT-SPI is available!")
    print()

    # Get diagnostic info
    diag = get_diagnostic_info()
    if diag.get('atspi_version'):
        print(f"AT-SPI Version: {diag['atspi_version']}")
    print()

    print("Interactive Testing Mode")
    print("-" * 70)
    print()
    print("Instructions:")
    print("1. Press Enter (or type command)")
    print("2. You have 3 seconds to click on the app you want to test")
    print("3. The script will detect what app has focus after 3 seconds")
    print()
    print("Commands:")
    print("  [Enter]  - Detect focused app after 3 second delay")
    print("  'test'   - Insert test text via AT-SPI (with 3 second delay)")
    print("  'quit'   - Exit")
    print()

    import time

    while True:
        try:
            user_input = input("\n[Press Enter to detect, 'test' to insert, 'quit' to exit]: ").strip().lower()

            if user_input == 'quit':
                print("\nExiting...")
                break

            # Give user time to switch windows
            print("\n⏳ You have 3 seconds to click on the app you want to test...")
            for i in range(3, 0, -1):
                print(f"   {i}...", end='', flush=True)
                time.sleep(1)
            print(" detecting now!\n")

            # Get current context
            context = get_focused_context()

            if not context:
                print("\n⚠️  Could not detect focused application")
                print("   Make sure you clicked on an application window first")
                continue

            # Display context information
            print("\n" + "=" * 70)
            print("Focused Application Context")
            print("=" * 70)
            print(f"Application:     {context.app_name or '(unknown)'}")
            print(f"Widget Role:     {context.role or '(unknown)'}")
            print(f"Is Editable:     {'✅ Yes' if context.is_editable else '❌ No'}")
            print(f"Supports AT-SPI: {'✅ Yes' if context.supports_atspi else '❌ No'}")
            print(f"Has Selection:   {'✅ Yes' if context.has_selection else '❌ No'}")
            if context.has_selection:
                print(f"  Selection:     chars {context.selection_start} to {context.selection_end}")
            print(f"Caret Position:  {context.caret_offset}")
            print(f"Is Password:     {'⚠️  Yes (will skip)' if context.is_password else '❌ No'}")

            # Check if should use AT-SPI
            should_use, reason = should_use_atspi(context)
            print("\n" + "-" * 70)
            print(f"Should use AT-SPI: {'✅ YES' if should_use else '❌ NO'}")
            print(f"Reason: {reason}")

            # Recommendation
            print("\n" + "-" * 70)
            if should_use:
                print("✅ RECOMMENDED: Use AT-SPI for text insertion")
                if context.has_selection:
                    print("   → Will replace selected text directly")
                else:
                    print("   → Will insert at cursor position")
            else:
                print("❌ RECOMMENDED: Fall back to ydotool/paste")
                if not context.is_editable:
                    print("   → Not a text field")
                elif context.is_password:
                    print("   → Password field (use fallback for security)")
                else:
                    print("   → App doesn't support AT-SPI EditableText")

            # If user typed 'test', try inserting text
            if user_input == 'test':
                print("\n" + "=" * 70)
                print("Testing Text Insertion via AT-SPI...")
                print("=" * 70)

                if not context.is_editable:
                    print("❌ Cannot test: Current widget is not editable")
                    print("   → Please focus on a text field and try again")
                    continue

                if context.is_password:
                    print("⚠️  Skipping password field (for security)")
                    continue

                test_text = "Hello from TalkType AT-SPI! "

                if context.has_selection:
                    print(f"ℹ️  Will replace selected text with: {test_text!r}")
                else:
                    print(f"ℹ️  Will insert at cursor position: {test_text!r}")

                confirm = input("\nProceed with insertion? [y/N]: ").strip().lower()
                if confirm == 'y':
                    success = insert_text_atspi(test_text, context)
                    if success:
                        print("✅ Text inserted successfully via AT-SPI!")
                    else:
                        print("❌ AT-SPI insertion failed - would fall back to ydotool")
                else:
                    print("Insertion cancelled")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

    print("\nTest complete!")


if __name__ == "__main__":
    main()
