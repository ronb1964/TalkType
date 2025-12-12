# MCP Screenshot Server - Usage Guide

## Quick Start

After restarting Claude Code, you'll have a new `take_screenshot` tool available.

## How to Use

### Basic Screenshot
```
User: "Take a screenshot"
Claude: [Calls take_screenshot tool]
Claude: [Can optionally read the screenshot to see what's on screen]
```

### Screenshot with Custom Filename
```
User: "Take a screenshot and save it as debug-ui.png"
Claude: [Calls take_screenshot with filename parameter]
```

### Screenshot and Analyze
```
User: "Take a screenshot of the TalkType preferences window and tell me if the colors look right"
Claude: [Takes screenshot]
Claude: [Reads screenshot to analyze]
Claude: "I can see the preferences window with..."
```

## Tool Details

### Function Signature
```
take_screenshot(
  filename: str = None,        # Optional: defaults to /tmp/screenshot_TIMESTAMP.png
  output_name: str = None      # Optional: descriptive name for the capture
)
```

### Returns
```json
{
  "success": true,
  "filename": "/tmp/screenshot_20251022_173500.png",
  "size": 2194861,
  "message": "Screenshot saved to /tmp/screenshot_20251022_173500.png (2194861 bytes)"
}
```

## Use Cases

### UI Development
- **Before making changes:** Take a screenshot
- **After making changes:** Take another screenshot
- **Compare:** Claude can see both and describe differences

### Bug Investigation
```
User: "The dialog doesn't look right. Take a screenshot and tell me what's wrong."
Claude: [Takes screenshot]
Claude: [Analyzes the image]
Claude: "I see the issue - the text is cut off at the bottom because..."
```

### Theme Testing
```
User: "Take screenshots while I switch between light and dark themes"
Claude: [Takes multiple screenshots]
Claude: "I can see both themes. In dark mode, the contrast looks good, but in light mode..."
```

### Cross-Desktop Testing
Works alongside the Docker testing infrastructure:
- Run TalkType in container
- Take screenshot via MCP
- Compare with expected UI

## Technical Notes

### Where Screenshots Are Saved
- **Default:** `/tmp/screenshot_TIMESTAMP.png`
- **Custom:** Anywhere you specify (must have write permission)
- **Recommendation:** Use `/tmp/` for temporary test screenshots

### Screenshot Tool Used
- Uses `gnome-screenshot` (already installed on Fedora/Nobara)
- Captures the entire screen
- Format: PNG

### Permissions
- No special permissions needed
- Works in Wayland and X11 sessions
- Requires GNOME desktop environment (or gnome-screenshot installed)

## Example Workflows

### Workflow 1: UI Iteration
```
1. User: "Take a screenshot of the current preferences window"
2. Claude: [Takes screenshot, shows filename]
3. User: "Change the button color to blue"
4. Claude: [Makes code changes]
5. User: "Take another screenshot"
6. Claude: [Takes second screenshot]
7. User: "Which looks better?"
8. Claude: [Can reference both screenshots to compare]
```

### Workflow 2: Bug Report
```
1. User: "I'm seeing a weird layout issue. Take a screenshot."
2. Claude: [Takes screenshot]
3. Claude: [Reads screenshot image]
4. Claude: "I can see the dialog is too tall for the window. This is happening in welcome_dialog.py:145..."
5. User: "Fix it"
6. Claude: [Makes fix]
7. User: "Take another screenshot to verify"
8. Claude: [Confirms fix worked]
```

### Workflow 3: Documentation
```
1. User: "Take screenshots of each preference tab"
2. Claude: [Takes 4-5 screenshots]
3. User: "Add these to the README with descriptions"
4. Claude: [Updates README.md with image references and descriptions]
```

## Advantages Over Manual Screenshots

### Without MCP (Old Way)
1. User presses Print Screen
2. Saves to ~/Pictures/Screenshots/
3. Types out the filename
4. Claude uses Read tool with the path
5. 4 steps, manual intervention

### With MCP (New Way)
1. User says "take a screenshot"
2. Claude does it automatically
3. 1 step, fully automated

## Troubleshooting

### "Tool not available"
- **Solution:** Restart Claude Code
- The MCP server needs to be loaded on startup

### "Screenshot failed"
- **Check:** Is gnome-screenshot installed?
  ```bash
  command -v gnome-screenshot
  ```
- **Install if needed:**
  ```bash
  sudo dnf install gnome-screenshot
  ```

### "Permission denied"
- **Check:** Write permission to target directory
- **Solution:** Use `/tmp/` which is always writable

### "Display not found"
- **Check:** Running in graphical session?
- **Solution:** Only works when X11/Wayland is active

## Best Practices

1. **Use descriptive names** for screenshots you want to keep
   ```
   take_screenshot("/tmp/before-theme-change.png")
   take_screenshot("/tmp/after-theme-change.png")
   ```

2. **Clean up temporary screenshots**
   ```bash
   rm /tmp/screenshot_*.png
   ```

3. **For documentation**, save to project directory:
   ```
   take_screenshot("/home/ron/Dropbox/projects/TalkType/docs/screenshots/preferences.png")
   ```

4. **For debugging**, use timestamp names (default) so they don't conflict

## Future Enhancements

Potential improvements to consider:
- [ ] Take screenshot of specific window only
- [ ] Select region interactively
- [ ] Add delay before capture
- [ ] Return screenshot as base64 (for small images)
- [ ] Video recording capability
- [ ] Annotations on screenshot

## Related Tools

- **GTK Inspector:** `./launch-gtk-inspector.sh` - Live UI debugging
- **Cross-DE Testing:** `./test-all-de.sh` - Automated testing across desktops
- **Manual Screenshots:** `~/Pictures/Screenshots/` - Can still read these with Read tool

---

**Happy Screenshotting! 📸**

The MCP screenshot server makes UI development much faster by eliminating the manual screenshot → save → tell Claude workflow.
