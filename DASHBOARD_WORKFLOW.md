# Dashboard Update Workflow - Best Practices

## Overview

There are **two locations** where your dashboard exists:

1. **Grafana (Live Dashboard)** - Running at `http://localhost:3000`
2. **File System (Version Control)** - At `monitoring/dashboards/microservices-dashboard.json`

Both should always be in sync!

---

## The Right Workflow

### Option 1: Edit in Grafana UI (Recommended for Quick Changes)

**Best for:** Quick panel adjustments, testing new visualizations, debugging

#### Steps:

```
1. Open Grafana Dashboard
   → http://localhost:3000/d/microservices-dashboard

2. Click "Edit" button (top right)

3. Make your changes:
   - Add/remove panels
   - Change queries
   - Update colors, legends, etc.
   - Adjust time ranges

4. Save the dashboard
   → Click "Save dashboard" button
   → Add optional change description
   → Click "Save"

5. Export the updated dashboard to file
   → curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' \
     | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json

6. Commit to Git
   → git add monitoring/dashboards/microservices-dashboard.json
   → git commit -m "Update dashboard: [description of changes]"
   → git push
```

---

### Option 2: Edit in File, Then Upload to Grafana

**Best for:** Large changes, scripting, version control first

#### Steps:

```
1. Edit the JSON file directly
   → monitoring/dashboards/microservices-dashboard.json

2. Validate the JSON (optional)
   → cat monitoring/dashboards/microservices-dashboard.json | jq . > /dev/null
   → If no error, JSON is valid

3. Upload to Grafana
   → Wrap the dashboard JSON in a Grafana payload:
   
   curl -s -X POST -u admin:admin \
     -H "Content-Type: application/json" \
     -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
     http://localhost:3000/api/dashboards/db

4. Verify in Grafana
   → Open http://localhost:3000/d/microservices-dashboard
   → Check that your changes appear

5. Commit to Git
   → git add monitoring/dashboards/microservices-dashboard.json
   → git commit -m "Update dashboard: [description of changes]"
   → git push
```

---

## Complete Workflow (The Safe Way)

Follow this sequence every time you modify the dashboard:

### If You Edited in Grafana UI:

```bash
# Step 1: Export from Grafana to file
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' \
  | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json

# Step 2: Verify the file was updated
ls -lah monitoring/dashboards/microservices-dashboard.json

# Step 3: Check git status
git status

# Step 4: Review changes
git diff monitoring/dashboards/microservices-dashboard.json

# Step 5: Commit
git add monitoring/dashboards/microservices-dashboard.json
git commit -m "Update dashboard: [describe what changed]"

# Step 6: Push
git push
```

### If You Edited the JSON File:

```bash
# Step 1: Validate JSON syntax
cat monitoring/dashboards/microservices-dashboard.json | jq . > /dev/null && echo "✅ Valid JSON"

# Step 2: Upload to Grafana
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db | jq '.status, .url'

# Step 3: Verify in browser
open http://localhost:3000/d/microservices-dashboard

# Step 4: Commit to git
git add monitoring/dashboards/microservices-dashboard.json
git commit -m "Update dashboard: [describe what changed]"

# Step 5: Push
git push
```

---

## Quick Reference Commands

### Export Current Dashboard from Grafana to File
```bash
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' \
  | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json
```

### Upload Dashboard File to Grafana
```bash
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db
```

### Validate JSON File
```bash
cat monitoring/dashboards/microservices-dashboard.json | jq . > /dev/null && echo "✅ Valid"
```

### View Dashboard in Browser
```bash
open http://localhost:3000/d/microservices-dashboard
```

### Check Dashboard Changes
```bash
git diff monitoring/dashboards/microservices-dashboard.json | head -50
```

---

## Key Dashboard IDs to Remember

| Item | Value |
|------|-------|
| **Dashboard UID** | `microservices-dashboard` |
| **Dashboard URL** | `http://localhost:3000/d/microservices-dashboard` |
| **Dashboard ID** | `2` (in Grafana, subject to change) |
| **Prometheus Datasource UID** | `PBFA97CFB590B2093` |
| **File Path** | `monitoring/dashboards/microservices-dashboard.json` |
| **Admin User** | `admin` |
| **Admin Password** | `admin` |

---

## Common Tasks

### Add a New Panel
1. Edit in Grafana UI (easier)
2. Click "Add Panel" → "Create new panel"
3. Configure your panel
4. Save dashboard
5. Export to file: `curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json`
6. Commit to git

### Change a Query
1. Edit in Grafana UI (Test live)
2. Click the panel title → "Edit"
3. Modify the query in the query editor
4. See results update in real-time
5. Click outside the editor to close
6. Save dashboard
7. Export to file
8. Commit to git

### Update Colors/Thresholds
1. Edit in Grafana UI
2. Click the panel title → "Edit"
3. Go to "Field options" or "Panel options"
4. Adjust colors, thresholds, etc.
5. See preview update in real-time
6. Save and export to file
7. Commit to git

### Reorganize Panels
1. Edit in Grafana UI
2. Click "Edit" button (top right)
3. Drag and resize panels
4. Save dashboard
5. Export to file
6. Commit to git

---

## Syncing with Team

### Pull Latest Dashboard from Git
```bash
git pull
# Local file updated

# Then upload to Grafana if needed:
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db
```

### Share Dashboard Changes with Team
```bash
# After making changes:
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' \
  | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json

git add monitoring/dashboards/microservices-dashboard.json
git commit -m "Update dashboard: Added payment latency panel"
git push

# Teammates can then pull and upload:
git pull
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db
```

---

## Troubleshooting

### Dashboard Changes Not Appearing
**Problem:** Edited in Grafana but file not updated

**Solution:**
```bash
# Export from Grafana to file
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/microservices-dashboard' \
  | jq '.dashboard' > monitoring/dashboards/microservices-dashboard.json
```

### File Changes Not Appearing in Grafana
**Problem:** Edited file but Grafana still shows old dashboard

**Solution:**
```bash
# Upload file to Grafana
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db

# Then refresh Grafana browser: Ctrl+Shift+R
```

### JSON Syntax Error
**Problem:** Can't upload dashboard, error about invalid JSON

**Solution:**
```bash
# Validate JSON
cat monitoring/dashboards/microservices-dashboard.json | jq . > /dev/null

# If error shown, fix the JSON file
# Check the error location in the file
```

### Upload Returns "Bad Request"
**Problem:** curl returns "bad request data"

**Solution:** Make sure to wrap dashboard in proper format:
```bash
# ✅ Correct format:
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/dashboards/microservices-dashboard.json), \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db

# ❌ Wrong (missing wrapper):
curl -s -X POST -u admin:admin \
  -H "Content-Type: application/json" \
  -d @monitoring/dashboards/microservices-dashboard.json \
  http://localhost:3000/api/dashboards/db
```

---

## Summary

### The Golden Rule
**Keep Grafana and File Always in Sync!**

```
┌─────────────────────────┐
│   Make Changes in       │
│   Grafana UI or File    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Save/Commit Changes    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Export Grafana → File   │
│ OR                      │
│ Upload File → Grafana   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Commit File to Git      │
└─────────────────────────┘
```

### Recommended Approach
1. **Make quick changes** → Edit in Grafana UI (test live)
2. **Export to file** → Ensure file is up to date
3. **Commit to git** → Save changes to version control
4. **Push to team** → Share with teammates

This ensures:
- ✅ Changes are saved
- ✅ Changes are tested
- ✅ Changes are version controlled
- ✅ Team can access updates
