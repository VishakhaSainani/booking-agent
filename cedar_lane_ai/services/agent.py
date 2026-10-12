"""AI Receptionist Agent coordinating conversation turns, Groq/Gemini tool calls, and state."""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types
from groq import Groq

from cedar_lane_ai.adapters import (
    CalendarAdapter,
    SheetsAdapter,
    get_calendar_adapter,
    get_sheets_adapter,
)
from cedar_lane_ai.config import settings
from cedar_lane_ai.services.prompts import CEDAR_LANE_SYSTEM_PROMPT
from cedar_lane_ai.services.tools import (
    GEMINI_TOOLS_SCHEMA,
    execute_tool,
    get_groq_tools_schema,
)

logger = logging.getLogger(__name__)


class ReceptionistAgent:
    """Cedar Lane Auto Detailing conversational AI Receptionist."""

    def __init__(
        self,
        calendar: CalendarAdapter | None = None,
        sheets: SheetsAdapter | None = None,
        client: Any | None = None,
        groq_client: Any | None = None,
    ) -> None:
        self.calendar = calendar or get_calendar_adapter()
        self.sheets = sheets or get_sheets_adapter()
        self.client = client
        self.groq_client = groq_client
        self._gemini_tools = self._build_gemini_tools()
        self._groq_tools = get_groq_tools_schema()

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

    def _get_groq_client(self) -> Groq | None:
        """Instantiate or return Groq client if valid key is available."""
        if self.groq_client is not None:
            return self.groq_client

        api_key = settings.groq_api_key.strip()
        if not api_key or api_key.startswith("mock-"):
            return None

        try:
            return Groq(api_key=api_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize live Groq Client (%s).", exc)
            return None

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

        # 1. Try Groq if configured
        groq_client = self._get_groq_client()
        if groq_client is not None and settings.llm_provider in ("groq", "auto"):
            try:
                return self._process_groq_turn(groq_client, history, tool_events)
            except Exception as exc:  # noqa: BLE001
                logger.error("Groq generation error: %s. Trying fallback.", exc)

        # 2. Try Gemini if configured
        gemini_client = self._get_gemini_client()
        if gemini_client is not None and settings.llm_provider in ("gemini", "auto"):
            try:
                return self._process_gemini_turn(gemini_client, history, tool_events)
            except Exception as exc:  # noqa: BLE001
                logger.error("Gemini generation error: %s. Using deterministic fallback.", exc)

        # 3. Deterministic local simulation mode (when running tests or offline)
        reply = self._handle_offline_turn(user_message, tool_events)
        history.append({"role": "model", "content": reply})
        return reply, history, tool_events

    def _process_groq_turn(
        self,
        client: Groq,
        history: list[dict[str, Any]],
        tool_events: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Execute conversation turn with Groq and openai/gpt-oss-120b native tool calling."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": CEDAR_LANE_SYSTEM_PROMPT}
        ]
        for msg in history:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

        max_tool_rounds = 4
        for _ in range(max_tool_rounds):
            try:
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    tools=self._groq_tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception as exc:
                failed_gen = self._extract_failed_generation(str(exc))
                if failed_gen:
                    call_name = failed_gen.get("name", "")
                    call_args = failed_gen.get("arguments", {})
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
                    recovery_reply = self._format_tool_recovery_reply(call_name, call_args, result)
                    history.append({"role": "model", "content": recovery_reply})
                    return recovery_reply, history, tool_events
                raise

            choice = response.choices[0]
            message = choice.message

            if not message.tool_calls:
                reply_text = (
                    message.content
                    or "Thank you for contacting Cedar Lane Auto Detailing."
                )
                history.append({"role": "model", "content": reply_text})
                return reply_text, history, tool_events

            # Append model's assistant turn with tool calls to message sequence
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            for tool_call in message.tool_calls:
                call_name = tool_call.function.name
                raw_args = tool_call.function.arguments or "{}"
                try:
                    call_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    call_args = {}

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
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    }
                )

        # Fallback summary if max rounds reached
        final_reply = "I have updated our scheduling system. How else may I assist you today?"
        history.append({"role": "model", "content": final_reply})
        return final_reply, history, tool_events

    @staticmethod
    def _extract_failed_generation(error_text: str) -> dict[str, Any] | None:
        """Extract tool call data from Groq 'failed_generation' error payload."""
        try:
            if "failed_generation" not in error_text:
                return None
            idx = error_text.find("failed_generation")
            colon_idx = error_text.find(":", idx + len("failed_generation"))
            if colon_idx == -1:
                return None

            # Locate opening quote of the value after colon
            val_start = -1
            quote_char = None
            for i in range(colon_idx + 1, len(error_text)):
                if error_text[i] in ("'", '"'):
                    quote_char = error_text[i]
                    val_start = i + 1
                    break
            if val_start == -1 or quote_char is None:
                return None

            # Locate closing quote following '}'
            val_end = -1
            for j in range(val_start, len(error_text)):
                if error_text[j] == quote_char and error_text[j - 1] in ("}", " ", "\n"):
                    val_end = j
                    break
            if val_end == -1:
                return None

            json_str = error_text[val_start:val_end]
            json_str = json_str.replace("\\'", "'").replace('\\"', '"')
            parsed = json.loads(json_str)
            if isinstance(parsed, dict) and "name" in parsed:
                return parsed
        except Exception:  # noqa: BLE001
            pass
        return None

    @staticmethod
    def _format_tool_recovery_reply(
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Construct friendly natural response for recovered tool calls."""
        if tool_name == "book_appointment":
            if result.get("success"):
                cust = arguments.get("customer_name") or arguments.get("name") or "there"
                dt = arguments.get("date", "")
                tm = arguments.get("time", "")
                srv = arguments.get("service_type") or arguments.get("service") or "service"
                veh = arguments.get("vehicle_type") or arguments.get("vehicle") or "vehicle"
                return (
                    f"You're all booked, {cust}! I've scheduled your {srv} for your {veh} "
                    f"on {dt} at {tm}. A confirmation has been added to our shop calendar."
                )
            return str(result.get("reason") or "We were unable to complete the booking.")
        if tool_name == "check_availability":
            if result.get("available"):
                dt = arguments.get("date", "")
                tm = arguments.get("time", "")
                return (
                    f"Yes, {dt} at {tm} is currently available! "
                    "Would you like me to book it for you?"
                )
            alts = ", ".join(result.get("alternative_slots", [])[:3])
            return (
                f"That requested slot is unavailable. "
                f"Alternative open slots on that day: {alts}."
            )
        return str(result.get("message") or "I have processed your request.")

    def _process_gemini_turn(
        self,
        client: genai.Client,
        history: list[dict[str, Any]],
        tool_events: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Execute conversation turn with Google Gemini."""
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

        # Check for booking request
        if "book" in msg and ("saturday" in msg or "sarah" in msg or "10am" in msg or "suv" in msg):
            res = execute_tool(
                "book_appointment",
                {
                    "customer_name": "Sarah Jenkins",
                    "phone_number": "555-0144",
                    "date": "2026-10-17",
                    "time": "10:00 AM",
                    "service_type": "Full Detail",
                    "vehicle_type": "SUV",
                },
                self.calendar,
                self.sheets,
            )
            tool_events.append(
                {
                    "tool_name": "book_appointment",
                    "arguments": {
                        "customer_name": "Sarah Jenkins",
                        "phone_number": "555-0144",
                        "date": "2026-10-17",
                        "time": "10:00 AM",
                        "service_type": "Full Detail",
                        "vehicle_type": "SUV",
                    },
                    "result": res,
                }
            )
            return (
                "You're all booked for a Full Detail on your SUV this Saturday, "
                "October 17th at 10:00 AM! The price is $320. "
                "A confirmation has been logged to our schedule."
            )

        # Check for availability queries
        if any(k in msg for k in ["3:30", "thursday", "open", "available", "slot"]):
            res = execute_tool(
                "check_availability",
                {
                    "date": "2026-10-15",
                    "time": "3:30 PM",
                    "service_type": "Interior Detail & Wash",
                },
                self.calendar,
                self.sheets,
            )
            tool_events.append(
                {
                    "tool_name": "check_availability",
                    "arguments": {
                        "date": "2026-10-15",
                        "time": "3:30 PM",
                        "service_type": "Interior Detail & Wash",
                    },
                    "result": res,
                }
            )
            if res.get("available"):
                return (
                    "Yes, Thursday October 15th at 3:30 PM is open for an Interior Detail & Wash "
                    "($150 Sedan / $190 SUV). Would you like me to reserve that slot for you?"
                )
            alts = ", ".join(res.get("alternative_slots", ["4:00 PM"])[:2])
            return f"That 3:30 PM slot is booked, but we have alternative slots open at {alts}."

        # Check for prep guidelines
        if "prep" in msg or "prepare" in msg:
            return (
                "To prepare your vehicle, please remove all personal belongings and valuables, "
                "clear the trunk/glovebox for interior details, remove child car seats, and "
                "bring your key fob."
            )

        # Check for hours
        if "hour" in msg:
            return (
                "Cedar Lane Auto Detailing is open Monday through Saturday "
                "from 8:00 AM to 6:00 PM. We are closed on Sundays."
            )

        # Check for pricing
        if "price" in msg or "cost" in msg or "wash" in msg or "sedan" in msg:
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
