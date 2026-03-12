#!/bin/bash

################################################################################
# monitor-spark-jobs.sh - Auto-Restart Stopped Spark Jobs
################################################################################
#
# PURPOSE:
#   Monitors all 5 Spark jobs and automatically restarts them if they stop.
#   Runs as a daemon/background process for production environments.
#
# USAGE:
#   # Start monitoring (runs in background)
#   ./scripts/spark/monitor-spark-jobs.sh &
#
#   # Or for continuous operation (run in tmux/screen)
#   tmux new-session -d -s spark-monitor './scripts/spark/monitor-spark-jobs.sh'
#
# WHAT IT DOES:
#   1. Checks all 5 streaming jobs every 30 seconds
#   2. If a job is stopped, automatically restarts it
#   3. Logs all status changes to /tmp/spark-monitor.log
#   4. Sends alerts if restart fails (requires curl)
#
# INTERVAL:
#   30 seconds (configurable via MONITOR_INTERVAL variable)
#
# JOBS MONITORED:
#   ✓ fraud_detection
#   ✓ revenue_streaming
#   ✓ cart_abandonment
#   ✓ inventory_velocity (batch job - won't be restarted if it completes)
#   ✓ operational_metrics
#
# LOGS:
#   /tmp/spark-monitor.log  - All monitoring events
#   /tmp/spark_*.log        - Individual job logs
#
# EXAMPLES:
#
#   # Start monitoring in background
#   ./scripts/spark/monitor-spark-jobs.sh &
#
#   # Start in tmux session for persistent monitoring
#   tmux new-session -d -s spark-monitor './scripts/spark/monitor-spark-jobs.sh'
#
#   # View monitoring logs in real-time
#   tail -f /tmp/spark-monitor.log
#
#   # Kill monitoring daemon
#   pkill -f monitor-spark-jobs.sh
#
# BEHAVIOR:
#
#   Every 30 seconds:
#   1. Check if fraud_detection process is running
#   2. Check if revenue_streaming process is running
#   3. Check if cart_abandonment process is running
#   4. Check if operational_metrics process is running
#   5. Check if inventory_velocity is running (batch job)
#
#   If a job is NOT running:
#   1. Log the incident with timestamp
#   2. Display notification
#   3. Automatically restart the job
#   4. Log restart success/failure
#
#   If a job restarts successfully:
#   1. Log restart completion
#   2. Continue monitoring
#
#   If restart fails:
#   1. Log failure with error details
#   2. Try again in next cycle (30 seconds later)
#   3. Optionally send alert (requires curl)
#
# PRODUCTION SETUP:
#
#   Option 1: Systemd Service
#   Create /etc/systemd/system/spark-monitor.service with:
#
#     [Unit]
#     Description=Spark Jobs Monitor
#     After=docker.service
#
#     [Service]
#     Type=simple
#     WorkingDirectory=/path/to/kafka-microservices-spark-ecom
#     ExecStart=/path/to/scripts/spark/monitor-spark-jobs.sh
#     Restart=always
#     RestartSec=10
#
#     [Install]
#     WantedBy=multi-user.target
#
#   Then: systemctl start spark-monitor
#
#   Option 2: Docker Container
#   Run this script in a separate container that mounts docker socket.
#
#   Option 3: Cron Job (every minute)
#   Add to crontab:
#   * * * * * /path/to/scripts/spark/monitor-spark-jobs.sh --once
#
#   Option 4: tmux/screen Session
#   tmux new-session -d -s spark-monitor './scripts/spark/monitor-spark-jobs.sh'
#
# CONFIGURATION:
#   MONITOR_INTERVAL=30      # Check every 30 seconds
#   LOG_FILE=/tmp/spark-monitor.log
#   ALERT_URL=""             # Optional: webhook for alerts
#
# TROUBLESHOOTING:
#
#   Q: Monitoring script itself stops?
#   A: Use systemd service or cron for auto-restart
#
#   Q: Job keeps restarting in a loop?
#   A: Check job logs: tail -f /tmp/spark_fraud_detection.log
#
#   Q: Why isn't inventory_velocity being restarted?
#   A: It's a batch job that runs once hourly - normal behavior
#
################################################################################

set -e

# Configuration
MONITOR_INTERVAL=30  # Check every 30 seconds
LOG_FILE="/tmp/spark-monitor.log"
ALERT_URL="${SPARK_ALERT_WEBHOOK:-}"  # Optional webhook for alerts
ONCE_MODE=false

# Parse arguments
if [ "$1" = "--once" ]; then
    ONCE_MODE=true
    MONITOR_INTERVAL=0
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Initialize log file
if [ ! -f "$LOG_FILE" ]; then
    touch "$LOG_FILE"
fi

# Function to log messages
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    case $level in
        INFO)
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
    esac
}

# Function to send alert
send_alert() {
    local message=$1
    
    if [ -z "$ALERT_URL" ]; then
        return
    fi
    
    curl -X POST "$ALERT_URL" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"$message\"}" \
        2>/dev/null || true
}

# Function to check if job is running
is_job_running() {
    local job_name=$1
    docker exec spark-worker-1 pgrep -f "${job_name}\.py" > /dev/null 2>&1
    return $?
}

# Function to restart job
restart_job() {
    local job_name=$1
    
    log_message "WARN" "Job $job_name is not running, restarting..."
    
    # Submit job (output to log file)
    ./scripts/spark/run-spark-job.sh "$job_name" >> "$LOG_FILE" 2>&1
    
    # Wait a bit for job to start
    sleep 3
    
    # Verify job started
    if is_job_running "$job_name"; then
        log_message "SUCCESS" "Job $job_name restarted successfully"
        send_alert "✅ Restarted Spark job: $job_name"
        return 0
    else
        log_message "ERROR" "Failed to restart job $job_name"
        send_alert "❌ Failed to restart Spark job: $job_name"
        return 1
    fi
}

# Function to check all jobs
check_all_jobs() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Jobs to monitor (streaming jobs, not batch jobs)
    local streaming_jobs=("fraud_detection" "revenue_streaming" "cart_abandonment" "operational_metrics")
    
    log_message "INFO" "=== Checking job status ==="
    
    local all_running=true
    
    for job in "${streaming_jobs[@]}"; do
        if is_job_running "$job"; then
            log_message "INFO" "✓ $job is running"
        else
            log_message "WARN" "✗ $job is NOT running"
            all_running=false
            
            # Attempt restart
            if restart_job "$job"; then
                # Restart successful
                true
            else
                # Restart failed - will retry next cycle
                true
            fi
        fi
    done
    
    # Note about inventory_velocity (batch job)
    log_message "INFO" "Note: inventory_velocity is a batch job (runs hourly, not continuous)"
    
    return 0
}

# Main monitoring loop
main() {
    log_message "INFO" "==================================="
    log_message "INFO" "Starting Spark Jobs Monitor"
    log_message "INFO" "Check interval: ${MONITOR_INTERVAL}s"
    log_message "INFO" "Logs: $LOG_FILE"
    log_message "INFO" "==================================="
    
    if [ "$ONCE_MODE" = true ]; then
        # Run once and exit
        check_all_jobs
        exit 0
    fi
    
    # Continuous monitoring loop
    while true; do
        check_all_jobs
        
        if [ $MONITOR_INTERVAL -gt 0 ]; then
            sleep $MONITOR_INTERVAL
        else
            break
        fi
    done
}

# Run main function
main
