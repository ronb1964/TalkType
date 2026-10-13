# TuxTalk Icons

## Official Icon: TT_retro_square_light.svg

**This is the OFFICIAL TuxTalk icon.** All builds and launchers must use this icon.

### Files in this directory:

- ✅ **TT_retro_square_light.svg** - **OFFICIAL ICON** (retro square design with blue on white)
- 🔒 **OFFICIAL_ICON_DO_NOT_CHANGE.svg** - Read-only backup of the official icon
- 📝 **TT_retro_square_light-Inkscape.svg** - Inkscape working file (editable version)

### Unused/Legacy Icons:
- TT_retro_round_dark.png
- TT_retro_round_light.png
- TT_retro_square_dark.png
- TT_retro_square_gradient_light.png
- TT_retro_square_light.png (PNG version)
- TT_round_light.png
- TT_square_dark.png
- TT_square_gradient_light.png
- TT_square_light.png

## Important Notes

1. **DO NOT** replace or modify `TT_retro_square_light.svg`
2. **DO NOT** modify `OFFICIAL_ICON_DO_NOT_CHANGE.svg` (it's read-only)
3. The icon at the project root (`../io.github.ronb1964.TuxTalk.svg`) must always be a copy of this official icon
4. See `../ICON_DOCUMENTATION.md` for complete documentation

## If You Need to Edit the Icon

1. Work with `TT_retro_square_light-Inkscape.svg` in Inkscape
2. When satisfied, export as "Plain SVG" and save to `TT_retro_square_light.svg`
3. Copy to the project root: `cp TT_retro_square_light.svg ../io.github.ronb1964.TalkType.svg`
4. Update the protected backup: `chmod 644 OFFICIAL_ICON_DO_NOT_CHANGE.svg && cp TT_retro_square_light.svg OFFICIAL_ICON_DO_NOT_CHANGE.svg && chmod 444 OFFICIAL_ICON_DO_NOT_CHANGE.svg`
