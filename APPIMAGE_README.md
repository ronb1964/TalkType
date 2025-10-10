# TalkType AppImageHub Submission

## Files for AppImageHub

The following files are ready for submission to App ImageHub:

1. **io.github.ronb1964.TalkType.appdata.xml** - AppStream metadata
2. **io.github.ronb1964.TalkType.desktop** - Desktop entry file
3. **io.github.ronb1964.TalkType.svg** - Application icon

## Submission Process

To submit TalkType to AppImageHub:

1. Fork the repository: https://github.com/AppImage/appimage.github.io
2. Create a new directory: `database/TalkType/`
3. Copy these files into that directory:
   - `io.github.ronb1964.TalkType.appdata.xml`
   - `io.github.ronb1964.TalkType.desktop`
   - `icons/128x128/io.github.ronb1964.TalkType.png` (or .svg)
   - Optional: `screenshot.png`
4. Create a file `database/TalkType/package.json` with:
   ```json
   {
     "name": "TalkType",
     "description": "AI-powered speech recognition and dictation for Wayland",
     "categories": ["Utility", "AudioVideo", "Accessibility"],
     "license": "MIT",
     "links": [
       {
         "type": "GitHub",
         "url": "https://github.com/ronb1964/TalkType"
       },
       {
         "type": "Download",
         "url": "https://github.com/ronb1964/TalkType/releases"
       }
     ],
     "screenshots": []
   }
   ```
5. Submit a pull request to the appimage.github.io repository

## Current Status

- ✅ AppStream metadata created
- ✅ Desktop file created
- ✅ Icon created
- ⏳ Screenshot needed (optional but recommended)
- ⏳ Pull request to be submitted

## Notes

- The AppImage includes the metadata in `usr/share/metainfo/`
- The validation warnings about URLs are expected (they'll work once the repo is public)
- Screenshot can be added later if needed
