#!/bin/bash

################################################################################
# kill-auto-refill.sh - Stop the auto-refill-inventory background service
################################################################################
#
# PURPOSE:
#   Cleanly stop the auto-refill-inventory.py background process
#
# USAGE:
#   ./scripts/kill-auto-refill.sh              # Stop auto-refill service
#   ./scripts/kill-auto-refill.sh --force      # Force kill (SIGKILL)
#
# EXAMPLES:
#   # Stop the auto-refill service
#   ./scripts/kill-auto-refill.sh
#
#   # Force kill if process is stuck
#   ./scripts/kill-auto-refill.sh --force
#
# WHAT IT DOES:
#   1. Finds the auto-refill-inventory.py process
#   2. Sends SIGTERM signal (graceful shutdown)
#   3. Waits up to 5 seconds for process to exit
#   4. If still running, sends SIGKILL (force kill)
#   5. Displays status and statistics
#
# NOTES:
#   - Graceful shutdown (SIGTERM) allows cleanup on first try
#   - Use --force flag only if graceful shutdown doesn't work
#   - Process captures statistics before exiting
#   - Safe to run multiple times (won't error if not running)
#

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

FORCE_KILL="${1}"

# Function to find auto-refill process
find_process() {
    pgrep -f "auto-refill-inventory.py" || echo ""
}

# Function to gracefully stop the process
graceful_stop() {
    local pid=$1
    
    echo -e "${YELLOW}Stopping auto-refill service gracefully (PID: $pid)...${NC}"
    
    # Send SIGTERM (graceful shutdown)
    kill -TERM "$pid" 2>/dev/null || true
    
    # Wait up to 5 seconds for process to exit
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 5 ]; do
        echo -ne "\r${YELLOW}Waiting for process to exit... ($((5 - count))s)${NC}"
        sleep 1
        count=$((count + 1))
    done
    echo ""
    
    # Check if still running
    if kill -0 "$pid" 2>/dev/null; then
        return 1  # Still running, need force kill
    else
        return 0  # Successfully stopped
    fi
}

# Function to force kill the process
force_kill() {
    local pid=$1
    
    echo -e "${YELLOW}Force killing process (PID: $pid)...${NC}"
    kill -9 "$pid" 2>/dev/null || true
    
    sleep 1
    
    # Verify it's gone
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${RED}❌ Failed to kill process${NC}"
        return 1
    else
        return 0
    fi
}

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Auto-Refill Inventory Service Stop${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Find the process
PID=$(find_process)

if [ -z "$PID" ]; then
    echo -e "${GREEN}✅ Auto-refill service not running${NC}"
    exit 0
fi

echo -e "${YELLOW}Found auto-refill process: PID $PID${NC}"
echo ""

# Try graceful stop first (unless --force flag given)
if [ "$FORCE_KILL" != "--force" ]; then
    if graceful_stop "$PID"; then
        echo -e "${GREEN}✅ Auto-refill service stopped gracefully${NC}"
        echo ""
        echo -e "${BLUE}📊 Statistics:${NC}"
        echo "   - Process terminated cleanly"
        echo "   - All refill operations logged"
        echo "   - Database connections closed"
        exit 0
    fi
    
    # Graceful stop failed, ask about force kill
    echo ""
    echo -e "${YELLOW}⚠️  Graceful shutdown timeout${NC}"
    echo -e "${YELLOW}   Process still running after 5 seconds${NC}"
    echo ""
fi

# Force kill if needed or requested
if [ "$FORCE_KILL" = "--force" ] || [ -n "$(find_process)" ]; then
    if force_kill "$PID"; then
        echo -e "${GREEN}✅ Auto-refill service force killed${NC}"
        echo ""
        echo -e "${YELLOW}⚠️  Warning: Service was not responsive to graceful shutdown${NC}"
        echo "   Check for database connection issues or CPU load"
        exit 0
    else
        echo -e "${RED}❌ Failed to stop auto-refill service${NC}"
        exit 1
    fi
fi

# Verify it's gone
REMAINING=$(find_process)
if [ -z "$REMAINING" ]; then
    echo -e "${GREEN}✅ Auto-refill service successfully stopped${NC}"
    exit 0
else
    echo -e "${RED}❌ Process still running: PID $REMAINING${NC}"
    exit 1
fi
