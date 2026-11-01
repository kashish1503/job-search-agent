#!/usr/bin/env bash
# chmod +x start.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check .env exists
if [ ! -f .env ]; then
    echo "No .env found. Copy .env.example to .env and fill in your API key."
    echo "  cp .env.example .env"
    exit 1
fi

# Check resume dir
if [ ! -d ./resume ]; then
    echo "Warning: ./resume/ directory not found."
    echo "Mount your Overleaf project at ./resume/ for tailoring to work."
    echo "Continuing without resume tailoring..."
fi

echo "Starting OpenClaw..."
docker compose up --build -d

# Wait for service to be ready (up to 60s)
echo "Waiting for OpenClaw to start..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/config > /dev/null 2>&1; then
        echo "OpenClaw is ready!"
        open http://localhost:8000 2>/dev/null || echo "Open http://localhost:8000 in your browser."
        break
    fi
    sleep 2
done

echo ""
echo "To stop:  docker compose down"
echo "To logs:  docker compose logs -f"
