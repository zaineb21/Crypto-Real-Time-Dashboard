#!/bin/bash
# stop.sh — Stop all pipeline services

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[✔] $1${NC}"; }

echo ""
log "Stopping pipeline services..."

# Kill producer, spark, dashboard by saved PIDs
if [ -f .pids ]; then
  read PRODUCER_PID SPARK_PID DASHBOARD_PID < .pids
  kill "$PRODUCER_PID" "$SPARK_PID" "$DASHBOARD_PID" 2>/dev/null
  rm .pids
  log "Producer, Spark, Dashboard stopped."
else
  echo "No .pids file found — killing by name..."
  pkill -f "api_producer.py" 2>/dev/null
  pkill -f "streaming_app.py" 2>/dev/null
  pkill -f "streamlit" 2>/dev/null
fi

# Stop Docker
docker compose down
log "Kafka & Zookeeper stopped."

echo ""
log "All services stopped."