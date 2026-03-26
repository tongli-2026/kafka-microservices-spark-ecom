#!/bin/bash
# Setup script for DLQ Monitoring & Auto-Replay
# Installs dependencies, configures services, and starts monitoring

set -e

echo "🚀 DLQ Monitoring & Auto-Replay Setup"
echo "========================================"
echo ""

# Step 1: Check Python version
echo "1️⃣  Checking Python version..."
python --version

# Step 2: Install required Python packages
echo ""
echo "2️⃣  Installing Python dependencies..."
pip install --quiet confluent-kafka prometheus-client requests psycopg2-binary

# Step 3: Make scripts executable
echo ""
echo "3️⃣  Making scripts executable..."
chmod +x scripts/dlq-auto-replay.py
chmod +x scripts/dlq-replay.py

# Step 4: Verify Kafka connectivity
echo ""
echo "4️⃣  Testing Kafka connectivity..."
python -c "
from confluent_kafka.admin import AdminClient
try:
    admin = AdminClient({'bootstrap.servers': 'localhost:9094'})
    # Get metadata
    metadata = admin.list_topics(timeout=5)
    topics = metadata.topics
    print('✅ Kafka connection successful')
    print(f'   Found {len(topics)} topics')
    if 'dlq.events' in topics:
        print('✅ DLQ topic exists')
    else:
        print('⚠️  DLQ topic not found (will be created on first error)')
except Exception as e:
    print(f'❌ Kafka connection failed: {e}')
    exit(1)
"

# Step 5: Verify PostgreSQL connectivity
echo ""
echo "5️⃣  Testing PostgreSQL connectivity..."
python -c "
import os
import psycopg2
try:
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'kafka_ecom'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'postgres')
    )
    conn.close()
    print('✅ PostgreSQL connection successful')
except Exception as e:
    print(f'❌ PostgreSQL connection failed: {e}')
    exit(1)
"

# Step 6: Test auto-replay script
echo ""
echo "6️⃣  Testing DLQ auto-replay script..."
python scripts/dlq-auto-replay.py --threshold 50 --verbose

# Step 7: Show startup command
echo ""
echo "========================================"
echo "✅ Setup Complete!"
echo "========================================"
echo ""
echo "📊 Next Steps:"
echo ""
echo "1. Start DLQ Auto-Replay Daemon:"
echo "   nohup python scripts/dlq-auto-replay.py --daemon --interval 300 > logs/dlq-auto-replay.log 2>&1 &"
echo ""
echo "2. Verify Prometheus is collecting metrics:"
echo "   curl http://localhost:9090/api/v1/query?query=dlq_message_count"
echo ""
echo "3. Open Grafana dashboards:"
echo "   - Infrastructure Health: http://localhost:3000/d/infrastructure-health-dashboard"
echo "   - Microservices: http://localhost:3000/d/microservices-dashboard"
echo ""
echo "4. Generate test traffic to trigger DLQ:"
echo "   docker-compose stop postgres  # Simulate failure"
echo "   python scripts/simulate-users.py --duration 30 --users 5"
echo "   docker-compose up -d postgres  # Recover"
echo "   # Watch auto-replay trigger and DLQ clear"
echo ""
echo "📖 Documentation:"
echo "   - See: DLQ_MONITORING_IMPLEMENTATION.md"
echo "   - See: scripts/README.md (DLQ Recovery section)"
echo ""
