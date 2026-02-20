#!/bin/bash
#
# State Management Installation Test
# ===================================
# Verifies that all state management scripts are installed correctly.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo "STATE MANAGEMENT INSTALLATION TEST"
echo "======================================================================"
echo ""

ERRORS=0

# Check directory structure
echo "Checking directory structure..."

if [ ! -d "$SCRIPT_DIR/snapshots" ]; then
    echo -e "${YELLOW}⚠ Creating snapshots directory...${NC}"
    mkdir -p "$SCRIPT_DIR/snapshots"
fi

echo -e "${GREEN}✓ Directory structure OK${NC}"

# Check required files
echo ""
echo "Checking required files..."

REQUIRED_FILES=(
    "state-phase0.py"
    "state-phase1.py"
    "state-phase2.py"
    "state-restore.py"
    "snapshot-save.sh"
    "snapshot-restore.sh"
    "README.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file (missing)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check script executability
echo ""
echo "Checking script permissions..."

EXECUTABLE_FILES=(
    "state-phase0.py"
    "state-phase1.py"
    "state-phase2.py"
    "state-restore.py"
    "snapshot-save.sh"
    "snapshot-restore.sh"
)

for file in "${EXECUTABLE_FILES[@]}"; do
    if [ -x "$SCRIPT_DIR/$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file (executable)"
    else
        echo -e "  ${YELLOW}⚠${NC} $file (not executable, fixing...)"
        chmod +x "$SCRIPT_DIR/$file"
        echo -e "  ${GREEN}✓${NC} $file (now executable)"
    fi
done

# Check dependencies
echo ""
echo "Checking dependencies..."

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "  ${GREEN}✓${NC} Python: $PYTHON_VERSION"
else
    echo -e "  ${RED}✗${NC} Python 3 not found"
    ERRORS=$((ERRORS + 1))
fi

# Check for required Python modules
PYTHON_MODULES=("requests" "redis")

for module in "${PYTHON_MODULES[@]}"; do
    if python3 -c "import $module" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Python module: $module"
    else
        echo -e "  ${RED}✗${NC} Python module: $module (not installed)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check Docker
if command -v docker &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Docker installed"
else
    echo -e "  ${YELLOW}⚠${NC} Docker not found (needed for snapshots)"
fi

# Check dependent scripts
echo ""
echo "Checking dependent scripts..."

DEPENDENT_SCRIPTS=(
    "../reset-servers-api.py"
    "../test-phase1-all.py"
    "../phase2-invert-cables.py"
)

for script in "${DEPENDENT_SCRIPTS[@]}"; do
    if [ -f "$SCRIPT_DIR/$script" ]; then
        echo -e "  ${GREEN}✓${NC} $(basename $script)"
    else
        echo -e "  ${RED}✗${NC} $(basename $script) (missing)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test state-restore.py help
echo ""
echo "Testing state-restore.py..."

if python3 "$SCRIPT_DIR/state-restore.py" --help > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} state-restore.py --help works"
else
    echo -e "  ${RED}✗${NC} state-restore.py --help failed"
    ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
echo "======================================================================"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED${NC}"
    echo ""
    echo "State management system is ready to use!"
    echo ""
    echo "Quick start:"
    echo "  python state-restore.py 0  # Reset to Phase 0"
    echo "  python state-restore.py 1  # Advance to Phase 1"
    echo "  python state-restore.py 2  # Advance to Phase 2"
    echo ""
    echo "See README.md for full documentation"
else
    echo -e "${RED}✗ INSTALLATION INCOMPLETE${NC}"
    echo ""
    echo "Found $ERRORS error(s)"
    echo "Please fix the issues above before using the state management system"
fi

echo "======================================================================"

exit $ERRORS
