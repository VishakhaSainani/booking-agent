#!/usr/bin/env python3
"""CLI utility to provision, configure, and synchronize the Vapi Assistant.

Uses the Vapi REST API to configure:
- Deepgram Nova-2 STT (280ms endpointing)
- Cartesia Sonic TTS (TTFB < 100ms)
- Google Gemini LLM with low temperature (0.2)
- Cedar Lane deterministic tools pointing to your public webhook URL
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from urllib.error import HTTPError

from cedar_lane_ai.config import settings
from cedar_lane_ai.services.prompts import CEDAR_LANE_SYSTEM_PROMPT
from cedar_lane_ai.services.tools import GEMINI_TOOLS_SCHEMA

VAPI_BASE_URL = "https://api.vapi.ai"


def build_assistant_payload(webhook_url: str) -> dict:
    """Build the complete Vapi assistant specification."""
    vapi_tools = [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
            "server": {"url": webhook_url},
        }
        for schema in GEMINI_TOOLS_SCHEMA
    ]

    return {
        "name": "Cedar Lane AI Receptionist",
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en",
            "endpointing": 280,
            "smartFormat": True,
        },
        "model": {
            "provider": "google",
            "model": settings.gemini_model or "gemini-2.5-flash",
            "temperature": 0.2,
            "systemPrompt": CEDAR_LANE_SYSTEM_PROMPT,
            "tools": vapi_tools,
        },
        "voice": {
            "provider": "cartesia",
            "voiceId": "sonic-english",
            "model": "sonic-english",
        },
        "silenceTimeoutSeconds": 0.5,
        "maxDurationSeconds": 600,
        "firstMessage": (
            "Hello! Thank you for calling Cedar Lane Auto Detailing. "
            "How can I assist you with your vehicle today?"
        ),
        "serverUrl": webhook_url,
    }


def sync_vapi_assistant(dry_run: bool = False, webhook_url: str | None = None) -> None:
    """Synchronize local assistant definition with Vapi API."""
    api_key = settings.vapi_api_key.strip()
    if not api_key or api_key.startswith("your_"):
        print("❌ Error: VAPI_API_KEY is not configured in your .env file.", file=sys.stderr)
        sys.exit(1)

    target_webhook = (
        webhook_url
        or settings.webhook_url
        or "https://your-domain.ngrok-free.app/api/vapi/webhook"
    )
    payload = build_assistant_payload(target_webhook)

    print("====================================================================")
    print("🎙️ Cedar Lane Auto Detailing — Vapi Voice Provisioner")
    print(f"📡 Webhook Callback URL: {target_webhook}")
    print(f"🧠 Model: {payload['model']['model']} (Temp: {payload['model']['temperature']})")
    print("🎙️ Voice: Cartesia Sonic | STT: Deepgram Nova-2 (280ms endpointing)")
    print("====================================================================")

    if dry_run:
        print("\n🔍 DRY RUN: Formatted payload that would be sent to Vapi:")
        print(json.dumps(payload, indent=2))
        return

    assistant_id = settings.vapi_assistant_id.strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "CedarLane-AI/1.0",
    }

    if assistant_id and not assistant_id.startswith("your_"):
        url = f"{VAPI_BASE_URL}/assistant/{assistant_id}"
        method = "PATCH"
        print(f"\n🔄 Updating existing assistant on Vapi (ID: {assistant_id})...")
    else:
        url = f"{VAPI_BASE_URL}/assistant"
        method = "POST"
        print("\n✨ Creating new assistant on Vapi...")

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            res = json.loads(resp_body)
            assigned_id = res.get("id") or assistant_id
            print(f"✅ Successfully synchronized with Vapi! Assistant ID: {assigned_id}")
            print(f"🔗 Assistant Name: {res.get('name')}")
            print("\n💡 You can now make voice calls using:")
            print("1. In-browser web calling on your dashboard (http://localhost:8008)")
            print("2. Inbound phone calling connected in your Vapi dashboard.")
    except HTTPError as err:
        err_body = err.read().decode("utf-8")
        print(f"❌ Vapi API Error ({err.code}): {err_body}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parse CLI arguments and run provisioning."""
    parser = argparse.ArgumentParser(description="Vapi Assistant Setup Utility")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload without calling Vapi API",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        default="",
        help="Override webhook callback URL (e.g. ngrok HTTPS URL)",
    )
    args = parser.parse_args()
    sync_vapi_assistant(dry_run=args.dry_run, webhook_url=args.webhook_url or None)


if __name__ == "__main__":
    main()
