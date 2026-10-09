# Cedar Lane Auto Detailing — AI Receptionist

Autonomous AI Receptionist system for Cedar Lane Auto Detailing shop.

## Overview
- **Phase 1**: Core AI agent logic with tool calling, slot conflict handling, calendar sync, Google Sheets audit logging, and web chat UI.
- **Phase 2**: Real-time voice integration via Vapi (<1.2s response latency target).

## Project Setup
```bash
# 1. Create and activate virtual environment
uv venv --python 3.11 .venv
source .venv/bin/activate

# 2. Install dependencies
uv pip install -e ".[dev]"

# 3. Configure environment variables
cp .env.example .env
```
