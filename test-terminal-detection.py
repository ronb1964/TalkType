#!/usr/bin/env python3
"""
Test script to see what AT-SPI detects when focused on different applications.
Run this, then click into a terminal window within 5 seconds.
"""

import sys
import time

# Add src to path
sys.path.insert(0, 'src')

from talktype.atspi_helper import get_focused_context, is_terminal_active, _get_active_window_title, is_terminal_window_by_title

print("=" * 60)
print("Terminal Detection Test")
print("=" * 60)
print("\nYou have 5 seconds to click into a window...")
print("(Try: Cursor chat, Cursor terminal, VS Code terminal, etc.)")
print()

for i in range(5, 0, -1):
    print(f"{i}...")
    time.sleep(1)

print("\nDetecting focused application...\n")

# Get window title
window_title = _get_active_window_title()
print(f"📝 Window Title: {window_title!r}")
print()

# Check if it's a terminal by title
is_terminal_by_title = is_terminal_window_by_title()
print(f"🔍 Terminal by title: {is_terminal_by_title}")
print()

# Get AT-SPI context
context = get_focused_context()

if context:
    print("✅ AT-SPI Context Detected:")
    print(f"   App Name:     {context.app_name!r}")
    print(f"   Widget Role:  {context.role!r}")
    print(f"   Is Editable:  {context.is_editable}")
    print(f"   Supports ATSPI: {context.supports_atspi}")
    print()
else:
    print("❌ No AT-SPI context detected")
    print()

# Test terminal detection
is_terminal = is_terminal_active()
print(f"🎯 FINAL Terminal Detection Result: {is_terminal}")
print()

if is_terminal:
    print("✅ Will use Shift+Ctrl+V for paste")
else:
    print("✅ Will use Ctrl+V for paste")

print()
print("=" * 60)

