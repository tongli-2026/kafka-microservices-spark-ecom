#!/bin/bash

# ============================================================================
# dashboard-sync.sh - Sync Grafana Dashboard with File & Git
# ============================================================================
#
# USAGE:
#   ./scripts/dashboard-sync.sh export    # Export Grafana → file
#   ./scripts/dashboard-sync.sh upload    # Upload file → Grafana
#   ./scripts/dashboard-sync.sh commit    # Export + commit to git
#   ./scripts/dashboard-sync.sh sync      # Full sync: export + commit
#
# EXAMPLES:
#   # After editing in Grafana UI:
#   ./scripts/dashboard-sync.sh commit "Updated service status panels"
#
#   # After editing the JSON file:
#   ./scripts/dashboard-sync.sh upload
#
# ============================================================================

set -e

DASHBOARD_FILE="monitoring/dashboards/microservices-dashboard.json"
DASHBOARD_UID="microservices-dashboard"
GRAFANA_URL="http://localhost:3000"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Functions
# ============================================================================

check_dependencies() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}❌ Error: curl is not installed${NC}"
        exit 1
    fi
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}❌ Error: jq is not installed${NC}"
        exit 1
    fi
}

check_grafana_available() {
    if ! curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" "$GRAFANA_URL/api/datasources" > /dev/null 2>&1; then
        echo -e "${RED}❌ Error: Cannot connect to Grafana at $GRAFANA_URL${NC}"
        echo "   Make sure Grafana is running: docker-compose up -d grafana"
        exit 1
    fi
}

export_dashboard() {
    echo -e "${YELLOW}⬇️  Exporting dashboard from Grafana...${NC}"
    
    check_grafana_available
    
    # Export dashboard
    curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
        "$GRAFANA_URL/api/dashboards/uid/$DASHBOARD_UID" \
        | jq '.dashboard' > "$DASHBOARD_FILE"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Dashboard exported to $DASHBOARD_FILE${NC}"
        echo "   File size: $(du -h "$DASHBOARD_FILE" | cut -f1)"
    else
        echo -e "${RED}❌ Failed to export dashboard${NC}"
        exit 1
    fi
}

upload_dashboard() {
    echo -e "${YELLOW}⬆️  Uploading dashboard to Grafana...${NC}"
    
    # Validate file exists
    if [ ! -f "$DASHBOARD_FILE" ]; then
        echo -e "${RED}❌ Error: Dashboard file not found: $DASHBOARD_FILE${NC}"
        exit 1
    fi
    
    # Validate JSON
    if ! jq . "$DASHBOARD_FILE" > /dev/null 2>&1; then
        echo -e "${RED}❌ Error: Invalid JSON in $DASHBOARD_FILE${NC}"
        exit 1
    fi
    
    check_grafana_available
    
    # Upload dashboard
    RESPONSE=$(curl -s -X POST -u "$GRAFANA_USER:$GRAFANA_PASS" \
        -H "Content-Type: application/json" \
        -d "{\"dashboard\": $(cat "$DASHBOARD_FILE"), \"overwrite\": true}" \
        "$GRAFANA_URL/api/dashboards/db")
    
    STATUS=$(echo "$RESPONSE" | jq -r '.status // "error"')
    
    if [ "$STATUS" = "success" ]; then
        echo -e "${GREEN}✅ Dashboard uploaded successfully${NC}"
        echo "$RESPONSE" | jq '.url' | xargs -I {} echo "   URL: http://localhost:3000{}"
    else
        echo -e "${RED}❌ Failed to upload dashboard${NC}"
        echo "   Response: $RESPONSE"
        exit 1
    fi
}

validate_json() {
    echo -e "${YELLOW}🔍 Validating JSON...${NC}"
    
    if [ ! -f "$DASHBOARD_FILE" ]; then
        echo -e "${RED}❌ Error: File not found: $DASHBOARD_FILE${NC}"
        exit 1
    fi
    
    if jq . "$DASHBOARD_FILE" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ JSON is valid${NC}"
    else
        echo -e "${RED}❌ Invalid JSON in $DASHBOARD_FILE${NC}"
        jq . "$DASHBOARD_FILE" 2>&1 | head -20
        exit 1
    fi
}

show_diff() {
    echo -e "${YELLOW}📊 Changes to dashboard:${NC}"
    git diff --stat "$DASHBOARD_FILE" || echo "   No uncommitted changes"
}

commit_to_git() {
    local message="$1"
    
    if [ -z "$message" ]; then
        message="Update dashboard"
    fi
    
    echo -e "${YELLOW}📝 Committing to git...${NC}"
    
    if git status "$DASHBOARD_FILE" | grep -q "nothing to commit"; then
        echo -e "${YELLOW}ℹ️  No changes to commit${NC}"
        return 0
    fi
    
    git add "$DASHBOARD_FILE"
    git commit -m "$message"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Committed: $message${NC}"
        echo "   Use 'git push' to share with team"
    else
        echo -e "${RED}❌ Failed to commit${NC}"
        exit 1
    fi
}

full_sync() {
    local message="$1"
    
    echo -e "${YELLOW}🔄 Starting full sync...${NC}"
    echo ""
    
    export_dashboard
    echo ""
    
    validate_json
    echo ""
    
    show_diff
    echo ""
    
    commit_to_git "$message"
    echo ""
    
    echo -e "${GREEN}✅ Full sync complete!${NC}"
}

# ============================================================================
# Main
# ============================================================================

check_dependencies

case "${1:-help}" in
    export)
        export_dashboard
        ;;
    upload)
        upload_dashboard
        ;;
    commit)
        export_dashboard
        echo ""
        commit_to_git "${2:-Update dashboard}"
        ;;
    validate|check)
        validate_json
        ;;
    diff)
        show_diff
        ;;
    sync)
        full_sync "${2:-Update dashboard}"
        ;;
    help|--help|-h)
        cat << EOF
Dashboard Sync Tool - Synchronize Grafana Dashboard with File & Git

USAGE:
    ./scripts/dashboard-sync.sh <command> [arguments]

COMMANDS:
    export              Export dashboard from Grafana to file
    upload              Upload dashboard file to Grafana
    validate|check      Validate dashboard JSON syntax
    commit [msg]        Export dashboard and commit to git
    diff                Show changes to dashboard file
    sync [msg]          Full sync: export → validate → commit
    help                Show this help message

EXAMPLES:
    # After editing in Grafana UI, save to file and git:
    ./scripts/dashboard-sync.sh sync "Added payment metrics panel"
    
    # After editing JSON file, upload to Grafana:
    ./scripts/dashboard-sync.sh upload
    
    # Export current state from Grafana:
    ./scripts/dashboard-sync.sh export
    
    # Commit without exporting (if already exported):
    ./scripts/dashboard-sync.sh commit "Updated panel colors"

WORKFLOW:
    1. Edit dashboard in Grafana UI or JSON file
    2. Run: ./scripts/dashboard-sync.sh sync "Your message"
    3. This will:
       ✅ Export from Grafana (if edited in UI)
       ✅ Validate JSON
       ✅ Show what changed
       ✅ Commit to git
    4. Use 'git push' to share with team

TROUBLESHOOTING:
    - Grafana not running? docker-compose up -d grafana
    - JSON invalid? Edit monitoring/dashboards/microservices-dashboard.json
    - Want to see what changed? ./scripts/dashboard-sync.sh diff

EOF
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        echo "Run './scripts/dashboard-sync.sh help' for usage"
        exit 1
        ;;
esac
