#!/bin/bash
# Test script for dev environment

echo "=== Testing TalkType Dev Environment ==="
echo ""

# 1. Start the tray
echo "1. Starting tray icon..."
./run-dev.sh > /tmp/talktype-tray.log 2>&1 &
TRAY_PID=$!
sleep 3

# 2. Check if tray is running
if ps -p $TRAY_PID > /dev/null; then
    echo "   ✓ Tray started successfully (PID: $TRAY_PID)"
else
    echo "   ✗ Tray failed to start"
    echo "   Log:"
    cat /tmp/talktype-tray.log
    exit 1
fi

# 3. Check if app can import
echo ""
echo "2. Testing if dictation service can start..."
PYTHONPATH=./src .venv/bin/python -c "import talktype.app; print('   ✓ App module imports OK')" 2>&1

echo ""
echo "3. Checking running processes..."
ps aux | grep "[t]alktype" | awk '{print "   "$11" "$12" "$13}'

echo ""
echo "=== Test complete ==="
echo ""
echo "To stop: pkill -f talktype"
