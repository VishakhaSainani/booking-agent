"""AI Receptionist Agent coordinating conversation turns, Gemini tool calls, and state."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types

from cedar_lane_ai.adapters import (
    CalendarAdapter,
    SheetsAdapter,
    get_calendar_adapter,
    get_sheets_adapter,
)
from cedar_lane_ai.config import settings
from cedar_lane_ai.services.prompts import CEDAR_LANE_SYSTEM_PROMPT
from cedar_lane_ai.services.tools import GEMINI_TOOLS_SCHEMA, execute_tool

logger = logging.getLogger(__name__)


class ReceptionistAgent:
    """Cedar Lane Auto Detailing conversational AI Receptionist."""

    def __init__(
        self,
        calendar: CalendarAdapter | None = None,
        sheets: SheetsAdapter | None = None,
        client: Any | None = None,
    ) -> None:
        self.calendar = calendar or get_calendar_adapter()
        self.sheets = sheets or get_sheets_adapter()
        self.client = client
        self._gemini_tools = self._build_gemini_tools()

    def _build_gemini_tools(self) -> list[types.Tool]:
        """Convert tool schemas into Google GenAI types.Tool objects."""
        function_declarations = []
        for schema in GEMINI_TOOLS_SCHEMA:
            decl = types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        prop_name: types.Schema(
                            type=getattr(types.Type, prop_spec["type"]),
                            description=prop_spec["description"],
                        )
                        for prop_name, prop_spec in schema["parameters"]["properties"].items()
                    },
                    required=schema["parameters"].get("required", []),
                ),
            )
            function_declarations.append(decl)
        return [types.Tool(function_declarations=function_declarations)]

    def _get_gemini_client(self) -> genai.Client | None:
        """Instantiate or return Google GenAI client if valid key is available."""
        if self.client is not None:
            return self.client

        api_key = settings.gemini_api_key.strip()
        if not api_key or api_key.startswith("mock-"):
            return None

        try:
            return genai.Client(api_key=api_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize live Gemini Client (%s). Using fallback.", exc)
            return None

    def process_turn(
        self,
        user_message: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Process a conversation turn.

        Returns:
            (agent_reply_text, updated_conversation_history, executed_tool_events)
        """
        history = list(conversation_history or [])
        tool_events: list[dict[str, Any]] = []

        # Add user message to history
        history.append({"role": "user", "content": user_message})

        client = self._get_gemini_client()

        if client is None:
            # Deterministic local simulation mode (when running tests or offline)
            reply = self._handle_offline_turn(user_message, tool_events)
            history.append({"role": "model", "content": reply})
            return reply, history, tool_events

        try:
            # Convert history to Gemini contents format
            contents: list[types.Content] = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])],
                    )
                )

            config = types.GenerateContentConfig(
                system_instruction=CEDAR_LANE_SYSTEM_PROMPT,
                tools=self._gemini_tools,
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )

            # Check if model requested tool call(s)
            function_calls = response.function_calls
            if function_calls:
                tool_results_parts: list[types.Part] = []
                for call in function_calls:
                    call_name = call.name
                    call_args = call.args or {}
                    result = execute_tool(
                        tool_name=call_name,
                        arguments=call_args,
                        calendar=self.calendar,
                        sheets=self.sheets,
                    )
                    tool_events.append(
                        {
                            "tool_name": call_name,
                            "arguments": call_args,
                            "result": result,
                        }
                    )
                    tool_results_parts.append(
                        types.Part.from_function_response(
                            name=call_name,
                            response={"result": result},
                        )
                    )

                # Send tool results back to Gemini for final response
                followup_contents = list(contents)
                followup_contents.append(response.candidates[0].content)
                followup_contents.append(types.Content(role="user", parts=tool_results_parts))

                final_resp = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=followup_contents,
                    config=config,
                )
                final_text = (
                    final_resp.text
                    or "Thank you for contacting Cedar Lane Auto Detailing."
                )
                history.append({"role": "model", "content": final_text})
                return final_text, history, tool_events

            text = response.text or "Thank you for contacting Cedar Lane Auto Detailing."
            history.append({"role": "model", "content": text})
            return text, history, tool_events

        except Exception as exc:  # noqa: BLE001
            logger.error("Gemini generation error: %s. Using deterministic fallback.", exc)
            reply = self._handle_offline_turn(user_message, tool_events)
            history.append({"role": "model", "content": reply})
            return reply, history, tool_events

    def _handle_offline_turn(
        self,
        user_message: str,
        tool_events: list[dict[str, Any]],
    ) -> str:
        """Deterministic simulation for offline usage and tests."""
        msg = user_message.lower()

        # Check for complaints / damage
        is_complaint = any(k in msg for k in ["charge", "bill", "dispute", "scratch", "damage"])
        if is_complaint:
            reason = "Billing Dispute" if ("charge" in msg or "bill" in msg) else "Damage Claim"
            res = execute_tool(
                "escalate_to_human",
                {
                    "customer_name": "Valued Caller",
                    "phone_number": "555-0199",
                    "reason": reason,
                    "details": user_message,
                },
                self.calendar,
                self.sheets,
            )
            tool_events.append(
                {"tool_name": "escalate_to_human", "arguments": {}, "result": res}
            )
            return res.get("message", "I have logged this for our shop manager to contact you.")

        # Check for prep guidelines
        if "prep" in msg or "prepare" in msg:
            return (
                "To prepare your vehicle, please remove all personal belongings and valuables, "
                "clear the trunk/glovebox for interior details, remove child car seats, and "
                "bring your key fob."
            )

        # Check for pricing/hours
        if "hour" in msg or "open" in msg:
            return (
                "Cedar Lane Auto Detailing is open Monday through Saturday "
                "from 8:00 AM to 6:00 PM. We are closed on Sundays."
            )

        if "price" in msg or "cost" in msg:
            return (
                "Our services:\n"
                "- Express Wash & Vac (45 mins): $50 Sedan / $70 SUV\n"
                "- Interior Detail & Wash (90 mins): $150 Sedan / $190 SUV\n"
                "- Full Detail (3 hours): $250 Sedan / $320 SUV\n"
                "- Ceramic Coating ($800+): Requires custom manager quote."
            )

        return (
            "Hello! Welcome to Cedar Lane Auto Detailing. How can I help you today? "
            "I can check open appointment slots, book a service, or answer any shop questions."
        )
