#!/bin/bash
# start.sh — Launch the full real-time crypto pipeline
# Order: Docker (Kafka) → API Producer → Spark → Dashboard

set -e  # exit on error

# ─── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✔] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
fail() { echo -e "${RED}[✘] $1${NC}"; exit 1; }

# ─── Config ───────────────────────────────────────────────────────────────────
KAFKA_BROKER="localhost:9092"
COMPOSE_FILE="docker/docker-compose.yml"
SPARK_PACKAGES="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0"

PRODUCER_SCRIPT="src/api_producer.py"
SPARK_SCRIPT="src/streaming_app.py"
DASHBOARD_SCRIPT="src/dashboard.py"

# Use venv binaries directly
PYTHON="$(pwd)/venv/bin/python3"
STREAMLIT="$(pwd)/venv/bin/streamlit"

# Adjust paths if your scripts are at the root level
[ ! -f "$PRODUCER_SCRIPT" ] && PRODUCER_SCRIPT="api_producer.py"
[ ! -f "$SPARK_SCRIPT" ]    && SPARK_SCRIPT="streaming_app.py"
[ ! -f "$DASHBOARD_SCRIPT" ] && DASHBOARD_SCRIPT="dashboard.py"

# ─── Create logs directory if it doesn't exist ───────────────────────────────
mkdir -p logs

# ─── Step 1: Start Kafka via Docker Compose ───────────────────────────────────
echo ""
log "Step 1 — Starting Kafka & Zookeeper (Docker Compose)..."
docker compose -f "$COMPOSE_FILE" up -d || fail "Docker Compose failed. Is Docker running?"

# Wait for Kafka to be ready
warn "Waiting 15 seconds for Kafka to be ready..."
sleep 15

# ─── Step 2: Create Kafka topics ─────────────────────────────────────────────
echo ""
log "Step 2 — Creating Kafka topics..."

docker exec kafka kafka-topics --create \
  --bootstrap-server "$KAFKA_BROKER" \
  --topic crypto-topic \
  --partitions 1 \
  --replication-factor 1 \
  --if-not-exists 2>/dev/null && echo "  → crypto-topic OK"

docker exec kafka kafka-topics --create \
  --bootstrap-server "$KAFKA_BROKER" \
  --topic crypto-aggregates \
  --partitions 1 \
  --replication-factor 1 \
  --if-not-exists 2>/dev/null && echo "  → crypto-aggregates OK"

# ─── Step 3: Start API Producer in background ─────────────────────────────────
echo ""
log "Step 3 — Starting API Producer..."
$PYTHON "$PRODUCER_SCRIPT" > logs/producer.log 2>&1 &
PRODUCER_PID=$!
echo "  → PID: $PRODUCER_PID (logs: logs/producer.log)"

sleep 3

# ─── Step 4: Start Spark Streaming job in background ─────────────────────────
echo ""
log "Step 4 — Starting Spark Structured Streaming job..."
mkdir -p checkpoints/crypto-aggregates

spark-submit \
  --packages "$SPARK_PACKAGES" \
  "$SPARK_SCRIPT" > logs/spark.log 2>&1 &
SPARK_PID=$!
echo "  → PID: $SPARK_PID (logs: logs/spark.log)"

warn "Waiting 20 seconds for Spark to initialize..."
sleep 20

# ─── Step 5: Start Streamlit Dashboard ───────────────────────────────────────
echo ""
log "Step 5 — Starting Streamlit Dashboard..."
$STREAMLIT run "$DASHBOARD_SCRIPT" > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "  → PID: $DASHBOARD_PID (logs: logs/dashboard.log)"

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "All services started!"
echo ""
echo "  🌐 Dashboard  → http://localhost:8501"
echo "  🔥 Spark UI   → http://localhost:4040"
echo ""
echo "  PIDs:"
echo "    Producer  : $PRODUCER_PID"
echo "    Spark     : $SPARK_PID"
echo "    Dashboard : $DASHBOARD_PID"
echo ""
echo "  Logs in: ./logs/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
warn "To stop everything, run: bash stop.sh"

# Save PIDs for stop script
echo "$PRODUCER_PID $SPARK_PID $DASHBOARD_PID" > .pids