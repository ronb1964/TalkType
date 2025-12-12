#!/bin/bash
#
# Generate HTML comparison report from test screenshots
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SCREENSHOTS_DIR="$PROJECT_DIR/test-screenshots"
REPORT_FILE="$SCREENSHOTS_DIR/comparison-report.html"

echo "📊 Generating screenshot comparison report..."

# Find all screenshots
GNOME_SHOTS=($(find "$SCREENSHOTS_DIR" -name "*gnome*.png" | sort))
KDE_SHOTS=($(find "$SCREENSHOTS_DIR" -name "*kde*.png" | sort))
XFCE_SHOTS=($(find "$SCREENSHOTS_DIR" -name "*xfce*.png" | sort))

# Generate HTML report
cat > "$REPORT_FILE" << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TalkType Cross-Desktop Environment Test Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        header {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            margin-bottom: 2rem;
        }

        h1 {
            color: #2d3748;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: #718096;
            font-size: 1.1rem;
        }

        .timestamp {
            color: #a0aec0;
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }

        .comparison-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
            margin-bottom: 2rem;
        }

        .de-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .de-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 48px rgba(0, 0, 0, 0.15);
        }

        .de-header {
            padding: 1.5rem;
            font-weight: bold;
            font-size: 1.25rem;
            color: white;
            text-align: center;
        }

        .gnome-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .kde-header { background: linear-gradient(135deg, #0093e9 0%, #80d0c7 100%); }
        .xfce-header { background: linear-gradient(135deg, #8ec5fc 0%, #e0c3fc 100%); }

        .screenshot-container {
            padding: 1rem;
            background: #f7fafc;
        }

        .screenshot-img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            cursor: pointer;
            transition: transform 0.2s ease;
        }

        .screenshot-img:hover {
            transform: scale(1.02);
        }

        .screenshot-info {
            padding: 1rem;
            font-size: 0.9rem;
            color: #718096;
        }

        .no-screenshot {
            padding: 3rem;
            text-align: center;
            color: #a0aec0;
            font-style: italic;
        }

        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            cursor: pointer;
        }

        .modal-content {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            max-width: 90%;
            max-height: 90%;
        }

        .close-modal {
            position: absolute;
            top: 1rem;
            right: 2rem;
            color: white;
            font-size: 3rem;
            font-weight: bold;
            cursor: pointer;
            z-index: 1001;
        }

        footer {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            text-align: center;
            color: #718096;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #e2e8f0;
        }

        .stat {
            text-align: center;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #a0aec0;
            margin-top: 0.25rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🖥️ TalkType Cross-Desktop Test Report</h1>
            <p class="subtitle">Visual comparison across GNOME, KDE, and XFCE environments</p>
            <p class="timestamp">Generated: <span id="timestamp"></span></p>
        </header>

        <div class="comparison-grid">
            <!-- GNOME -->
            <div class="de-card">
                <div class="de-header gnome-header">GNOME</div>
                <div class="screenshot-container" id="gnome-container">
                    <div class="no-screenshot">No screenshots available</div>
                </div>
            </div>

            <!-- KDE -->
            <div class="de-card">
                <div class="de-header kde-header">KDE Plasma</div>
                <div class="screenshot-container" id="kde-container">
                    <div class="no-screenshot">No screenshots available</div>
                </div>
            </div>

            <!-- XFCE -->
            <div class="de-card">
                <div class="de-header xfce-header">XFCE</div>
                <div class="screenshot-container" id="xfce-container">
                    <div class="no-screenshot">No screenshots available</div>
                </div>
            </div>
        </div>

        <footer>
            <h3>Test Summary</h3>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value" id="total-screenshots">0</div>
                    <div class="stat-label">Total Screenshots</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="environments-tested">0</div>
                    <div class="stat-label">Environments Tested</div>
                </div>
                <div class="stat">
                    <div class="stat-value">✅</div>
                    <div class="stat-label">Status</div>
                </div>
            </div>
        </footer>
    </div>

    <!-- Image modal -->
    <div id="imageModal" class="modal" onclick="closeModal()">
        <span class="close-modal">&times;</span>
        <img class="modal-content" id="modalImage">
    </div>

    <script>
        // Set timestamp
        document.getElementById('timestamp').textContent = new Date().toLocaleString();

        // Screenshot data (will be replaced by script)
        const screenshots = SCREENSHOT_DATA;

        let totalScreenshots = 0;
        let environmentsTested = 0;

        function loadScreenshots(environment, containerID) {
            const container = document.getElementById(containerID);
            const shots = screenshots[environment] || [];

            if (shots.length > 0) {
                environmentsTested++;
                totalScreenshots += shots.length;
                container.innerHTML = '';
                shots.forEach((shot, index) => {
                    const img = document.createElement('img');
                    img.src = shot;
                    img.className = 'screenshot-img';
                    img.alt = `${environment} screenshot ${index + 1}`;
                    img.onclick = () => openModal(shot);
                    container.appendChild(img);

                    if (shots.length > 1) {
                        const info = document.createElement('div');
                        info.className = 'screenshot-info';
                        info.textContent = `Screenshot ${index + 1} of ${shots.length}`;
                        container.appendChild(info);
                    }
                });
            }
        }

        function openModal(imageSrc) {
            event.stopPropagation();
            const modal = document.getElementById('imageModal');
            const modalImg = document.getElementById('modalImage');
            modal.style.display = 'block';
            modalImg.src = imageSrc;
        }

        function closeModal() {
            document.getElementById('imageModal').style.display = 'none';
        }

        // Load screenshots for all environments
        loadScreenshots('gnome', 'gnome-container');
        loadScreenshots('kde', 'kde-container');
        loadScreenshots('xfce', 'xfce-container');

        // Update stats
        document.getElementById('total-screenshots').textContent = totalScreenshots;
        document.getElementById('environments-tested').textContent = environmentsTested;

        // Keyboard shortcut to close modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
    </script>
</body>
</html>
EOF

# Build screenshot data JSON in a temporary file
TEMP_DATA=$(mktemp)
echo "{" > "$TEMP_DATA"

# Add GNOME screenshots
echo "  gnome: [" >> "$TEMP_DATA"
for shot in "${GNOME_SHOTS[@]}"; do
    if [ -n "$shot" ]; then
        basename=$(basename "$shot")
        echo "    './$basename'," >> "$TEMP_DATA"
    fi
done
echo "  ]," >> "$TEMP_DATA"

# Add KDE screenshots
echo "  kde: [" >> "$TEMP_DATA"
for shot in "${KDE_SHOTS[@]}"; do
    if [ -n "$shot" ]; then
        basename=$(basename "$shot")
        echo "    './$basename'," >> "$TEMP_DATA"
    fi
done
echo "  ]," >> "$TEMP_DATA"

# Add XFCE screenshots
echo "  xfce: [" >> "$TEMP_DATA"
for shot in "${XFCE_SHOTS[@]}"; do
    if [ -n "$shot" ]; then
        basename=$(basename "$shot")
        echo "    './$basename'," >> "$TEMP_DATA"
    fi
done
echo "  ]" >> "$TEMP_DATA"
echo "};" >> "$TEMP_DATA"

# Replace the placeholder line with the actual data using awk
awk -v data="$(<"$TEMP_DATA")" '
    /const screenshots = SCREENSHOT_DATA;/ {
        print "        const screenshots = " data
        next
    }
    { print }
' "$REPORT_FILE" > "$REPORT_FILE.tmp"

mv "$REPORT_FILE.tmp" "$REPORT_FILE"
rm "$TEMP_DATA"

echo "✅ Report generated: $REPORT_FILE"
echo ""
echo "📊 To view the report:"
echo "  xdg-open '$REPORT_FILE'"
echo ""
echo "Or open in your browser:"
echo "  file://$REPORT_FILE"

# Auto-open if xdg-open is available
if command -v xdg-open &> /dev/null; then
    echo ""
    echo "🌐 Opening report in default browser..."
    xdg-open "$REPORT_FILE" &
fi
