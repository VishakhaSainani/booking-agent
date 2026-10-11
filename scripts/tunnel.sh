#!/usr/bin/env bash
# Quick script to expose local Cedar Lane server to public internet for Vapi webhook

PORT="${PORT:-8008}"

echo "========================================================================"
echo "🌐 Cedar Lane Auto Detailing — Public Tunnel for Vapi Webhook"
echo "Target Local Port: $PORT"
echo "========================================================================"

if command -v ngrok &> /dev/null; then
    echo "Starting ngrok on port $PORT..."
    echo "💡 Once running, copy the Forwarding URL (e.g. https://xyz.ngrok-free.app)"
    echo "   and set: WEBHOOK_URL=https://xyz.ngrok-free.app/api/vapi/webhook in your .env"
    echo "------------------------------------------------------------------------"
    exec ngrok http "$PORT"
else
    echo "ngrok not found. Trying localtunnel via npx..."
    if command -v npx &> /dev/null; then
        echo "Starting localtunnel on port $PORT..."
        exec npx -y localtunnel --port "$PORT"
    else
        echo "❌ Neither ngrok nor npx found."
        echo "Please install ngrok (brew install ngrok) or localtunnel to expose port $PORT."
        exit 1
    fi
fi
