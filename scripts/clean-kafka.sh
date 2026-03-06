#!/bin/bash

################################################################################
# clean-kafka.sh - Clean all Kafka topics and reset message queues
#
# PURPOSE:
#   Deletes all messages from Kafka topics to start with a clean slate
#   Useful for debugging and testing workflows
#
# USAGE:
#   echo "y" | ./clean-kafka.sh
#
# WARNING:
#   This will DELETE ALL KAFKA MESSAGES - use only for testing/development!
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Cleaning Kafka Topics${NC}"
echo ""

# Check if Kafka is running
if ! docker ps | grep -q kafka-broker-1; then
    echo -e "${RED}Error: Kafka broker not running${NC}"
    exit 1
fi

echo -e "${YELLOW}Getting list of all Kafka topics...${NC}"
TOPICS=$(docker exec kafka-broker-1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka-broker-1:9092 --list 2>/dev/null)

if [ -z "$TOPICS" ]; then
    echo -e "${RED}Error: Could not retrieve Kafka topics${NC}"
    exit 1
fi

echo -e "${GREEN}Found topics to clean:${NC}"
echo "$TOPICS" | while read topic; do
    if [ -n "$topic" ]; then
        echo "  • $topic"
    fi
done

echo ""
echo -e "${YELLOW}WARNING: This will delete ALL messages from all topics!${NC}"
echo -ne "${YELLOW}Continue? (y/N): ${NC}"
read -r -t 10 CONFIRM || CONFIRM="n"

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo -e "${YELLOW}Deleting topic configurations and messages...${NC}"

# For each topic, delete and recreate to clear messages
echo "$TOPICS" | while read topic; do
    if [ -n "$topic" ]; then
        echo -ne "  Processing $topic... "
        
        # Delete topic
        docker exec kafka-broker-1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka-broker-1:9092 \
            --delete --topic "$topic" > /dev/null 2>&1
        
        sleep 1
        
        # Recreate topic with same configuration
        docker exec kafka-broker-1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka-broker-1:9092 \
            --create --topic "$topic" --partitions 3 --replication-factor 3 \
            > /dev/null 2>&1 || true
        
        echo -e "${GREEN}✓${NC}"
    fi
done

echo ""
echo -e "${GREEN}✓ All Kafka topics cleaned${NC}"
echo ""

# Verify topics are empty
echo -e "${YELLOW}Verifying topics are empty...${NC}"
echo "$TOPICS" | while read topic; do
    if [ -n "$topic" ]; then
        COUNT=$(docker exec kafka-broker-1 kafka-run-class kafka.tools.GetOffsetShell \
            --broker-list localhost:9092 --topic "$topic" 2>/dev/null | \
            awk -F':' '{sum += $3} END {print sum}' || echo "0")
        
        echo "  • $topic: $COUNT messages"
    fi
done

echo ""
echo -e "${GREEN}Kafka cleanup complete!${NC}"
echo -e "${CYAN}Ready for fresh testing.${NC}"
