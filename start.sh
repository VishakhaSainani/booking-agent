#!/usr/bin/env bash
set -e

# Cedar Lane Auto Detailing — AI Receptionist Launch Script

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv --python 3.11 .venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
else
    source .venv/bin/activate
fi

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

echo "========================================================================"
echo "✨ Starting Cedar Lane Auto Detailing AI Receptionist Server..."
echo "📍 Web Dashboard & Chat: http://localhost:8000"
echo "📡 Vapi Webhook Endpoint: http://localhost:8000/api/vapi/webhook"
echo "🛠️ Assistant Blueprint:   http://localhost:8000/api/vapi/assistant-config"
echo "========================================================================"

exec uvicorn cedar_lane_ai.api.app:app --host 0.0.0.0 --port 8000 --reload
