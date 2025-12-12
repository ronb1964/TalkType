#!/bin/bash
#
# TalkType Visual Test Suite - One Command to Rule Them All
# Builds containers, runs tests, generates comparison report
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║        🧪 TalkType Visual Test Suite 🧪                   ║"
echo "║                                                            ║"
echo "║  Cross-Desktop Environment Testing & Visual Comparison    ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Parse arguments
BUILD_CONTAINERS=true
RUN_TESTS=true
GENERATE_REPORT=true
TEST_MODE="screenshot"

for arg in "$@"; do
    case $arg in
        --no-build)
            BUILD_CONTAINERS=false
            shift
            ;;
        --no-report)
            GENERATE_REPORT=false
            shift
            ;;
        --test-only)
            TEST_MODE="test"
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-build     Skip container building step"
            echo "  --no-report    Skip report generation"
            echo "  --test-only    Run pytest tests instead of screenshots"
            echo "  --help         Show this help message"
            echo ""
            echo "Default behavior:"
            echo "  1. Build all containers (GNOME, KDE, XFCE)"
            echo "  2. Take screenshots in each environment"
            echo "  3. Generate HTML comparison report"
            echo ""
            exit 0
            ;;
    esac
done

# Step 1: Build containers
if [ "$BUILD_CONTAINERS" = true ]; then
    echo "📦 Step 1/3: Building test containers..."
    echo ""
    cd docker-testing
    ./build-all.sh
    cd ..
    echo ""
else
    echo "⏭️  Skipping container build (using existing images)"
    echo ""
fi

# Step 2: Run tests
echo "🧪 Step 2/3: Running tests across desktop environments..."
echo ""
cd docker-testing
./run-tests.sh "$TEST_MODE"
cd ..
echo ""

# Step 3: Generate report (only for screenshot mode)
if [ "$TEST_MODE" = "screenshot" ] && [ "$GENERATE_REPORT" = true ]; then
    echo "📊 Step 3/3: Generating visual comparison report..."
    echo ""
    cd docker-testing
    ./generate-comparison-report.sh
    cd ..
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║  ✅ All tests completed successfully! ✅                   ║"
    echo "║                                                            ║"
    echo "║  📸 Screenshots: test-screenshots/                        ║"
    echo "║  📊 Report:      test-screenshots/comparison-report.html  ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
else
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║  ✅ Tests completed successfully! ✅                       ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
fi

# Show next steps
if [ "$TEST_MODE" = "screenshot" ]; then
    echo "🔍 Next steps:"
    echo "  • View report: xdg-open test-screenshots/comparison-report.html"
    echo "  • Run again without rebuild: $0 --no-build"
    echo "  • Run pytest tests: $0 --test-only"
fi

echo ""
