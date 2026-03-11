#!/bin/bash
#
# Hourly scheduler for inventory_velocity job
# Runs every hour to update product velocity rankings from PostgreSQL orders
#
# Setup: Add to crontab with: crontab -e
# Then add: 0 * * * * /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
#

# Source shell profile to get access to docker and other commands
# This is needed because cron runs in a minimal environment
if [ -f ~/.zshrc ]; then
    source ~/.zshrc
elif [ -f ~/.bash_profile ]; then
    source ~/.bash_profile
elif [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Explicitly add Docker to PATH if not already present
# Cron environment may not have full PATH, so we ensure docker is available
export PATH="/usr/local/bin:$PATH"

set -e

# Project root directory
PROJECT_ROOT="/Users/tong/KafkaProjects/kafka-microservices-spark-ecom"

# Log file location
LOG_FILE="/tmp/inventory_velocity_cron.log"

# Timestamp for logging
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log function
log_message() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

# Start logging
log_message "=========================================="
log_message "Starting inventory_velocity scheduled job"
log_message "=========================================="

# Change to project directory
cd "$PROJECT_ROOT" || {
    log_message "ERROR: Failed to change to project directory: $PROJECT_ROOT"
    exit 1
}

# Run the Spark job
log_message "Running: ./scripts/spark/run-spark-job.sh inventory_velocity"

if ./scripts/spark/run-spark-job.sh inventory_velocity >> "$LOG_FILE" 2>&1; then
    log_message "✅ Job completed successfully"
else
    log_message "❌ Job failed with exit code: $?"
    exit 1
fi

log_message "=========================================="
