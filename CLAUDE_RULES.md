claude

# CRITICAL RULES - READ EVERY SESSION

## NEVER RUN DESTRUCTIVE COMMANDS WITHOUT EXPLICIT USER PERMISSION

**DESTRUCTIVE COMMANDS INCLUDE:**
- `./fresh-start-dev.sh` - Deletes all dev config, data, models
- `./fresh-start-for-testing.sh` - Deletes AppImage config/data
- Any `rm -rf` commands
- `gsettings set` - Modifying GNOME settings
- Any script that deletes user files, configs, or data

**BEFORE running ANY destructive command:**
1. ASK: "I need to run [COMMAND] which will [EXPLAIN]. Is that okay?"
2. WAIT for explicit "yes" or "go ahead"
3. ONLY THEN proceed

**Exception:** User explicitly requested it in their current message

**REMEMBER: PRESERVE USER DATA ABOVE ALL ELSE**