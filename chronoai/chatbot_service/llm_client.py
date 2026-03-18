"""
chronoai/chatbot_service/llm_client.py — ChronoBotLLMClient
Wrapper around Hugging Face InferenceClient for ChronoBot.
Handles model selection, streaming, tool-call parsing, and rate-limit fallback.
"""

from __future__ import annotations

import json
import os
import re
from typing import Generator

from chronoai.config import get_settings

settings = get_settings()


class ChronoBotLLMClient:
    """
    HuggingFace InferenceClient wrapper for ChronoBot.

    Responsibilities:
    - Format prompts using Mistral/Zephyr [INST] template
    - Stream tokens from HF Inference API with automatic fallback
    - Parse <tool_call>...</tool_call> JSON blocks from model output
    - Track daily request counts for rate limit management
    """

    def __init__(self) -> None:
        from huggingface_hub import InferenceClient  # lazy import
        self.token = settings.hf_api_token
        self.primary_model = settings.hf_primary_model
        self.fallback_model = settings.hf_fallback_model
        self.fast_model = settings.hf_fast_model
        self.client = InferenceClient(token=self.token)

    # ── Prompt formatting ─────────────────────────────────────────
    def format_prompt(
        self,
        system: str,
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        """
        Format using Mistral/Zephyr chat template: [INST] ... [/INST]

        Args:
            system:       System prompt (injected once at start)
            history:      List of {role: user|assistant, content: str}
            user_message: Current user message

        Returns:
            Formatted prompt string ready for text_generation()
        """
        prompt = f"<s>[INST] {system}\n\n"
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                prompt += f"User: {content}\n"
            else:
                prompt += f"Assistant: {content}\n"
        prompt += f"User: {user_message} [/INST]"
        return prompt

    # ── Streaming ─────────────────────────────────────────────────
    def stream_response(
        self,
        prompt: str,
        model: str | None = None,
    ) -> Generator[str, None, None]:
        """
        Stream tokens from HF Inference API with automatic fallback to secondary model.

        Args:
            prompt: Full formatted prompt string
            model:  Override model ID (defaults to primary_model)

        Yields:
            Token strings as they arrive from the API
        """
        target_model = model or self.primary_model
        try:
            for token in self.client.text_generation(
                prompt,
                model=target_model,
                stream=True,
                max_new_tokens=settings.hf_max_new_tokens,
                temperature=settings.hf_temperature,
                top_p=settings.hf_top_p,
                repetition_penalty=settings.hf_repetition_penalty,
                return_full_text=False,
            ):
                yield token
        except Exception as e:
            if target_model == self.primary_model:
                # Auto-fallback to secondary model
                yield from self.stream_response(prompt, model=self.fallback_model)
            else:
                raise RuntimeError(
                    f"Both primary ({self.primary_model}) and fallback ({self.fallback_model}) "
                    f"models failed. Last error: {e}"
                ) from e

    def complete(self, prompt: str, model: str | None = None) -> str:
        """Non-streaming completion — collects all streamed tokens."""
        return "".join(self.stream_response(prompt, model))

    # ── Tool call parsing ────────────────────────────────────────
    def parse_tool_calls(self, response_text: str) -> list[dict[str, object]]:
        """
        Extract tool call JSON blocks from model output.
        The model is instructed to wrap tool calls in <tool_call>...</tool_call> tags.

        Args:
            response_text: Full model response string

        Returns:
            List of parsed tool call dicts: [{name: str, arguments: dict}, ...]
        """
        pattern = r"<tool_call>(.*?)</tool_call>"
        matches = re.findall(pattern, response_text, re.DOTALL)
        tool_calls: list[dict[str, object]] = []
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                tool_calls.append(parsed)
            except json.JSONDecodeError:
                # Attempt partial fix — wrap bare key:value as valid JSON
                try:
                    fixed = "{" + match.strip().strip("{}") + "}"
                    tool_calls.append(json.loads(fixed))
                except json.JSONDecodeError:
                    pass
        return tool_calls

    # ── Model management ─────────────────────────────────────────
    def get_available_models(self) -> list[str]:
        """Return list of configured free HF models for the Settings UI."""
        return [
            "mistralai/Mistral-7B-Instruct-v0.3",
            "HuggingFaceH4/zephyr-7b-beta",
            "meta-llama/Meta-Llama-3-8B-Instruct",
            "tiiuae/falcon-7b-instruct",
            "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        ]

    def get_model_for_load(self, daily_request_count: int) -> str:
        """
        Select model based on daily rate-limit usage.
        Switches to fast model when approaching free tier limit (~1000 req/day).
        """
        if daily_request_count >= 900:
            return self.fast_model  # TinyLlama for low quota
        if daily_request_count >= 700:
            return self.fallback_model  # Zephyr mid-range
        return self.primary_model  # Mistral default


# ── System prompt for ChronoBot ───────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """You are ChronoBot, an expert university scheduling assistant embedded within the ChronoAI timetable management system. You help faculty members view, understand, and modify their timetables and the timetables of sections they teach.

YOUR CAPABILITIES:
1. Answer questions about any section's current timetable
2. Explain why a class is scheduled at a particular time
3. Propose and apply timetable modifications at the faculty's request
4. Check and explain constraint violations before applying any change
5. Handle batch modifications across multiple sections simultaneously
6. Suggest optimal time slots when a faculty requests a move
7. Show the impact of a proposed change on all affected parties

YOUR CONSTRAINTS (NEVER VIOLATE):
- Never apply a change that creates a room conflict (HC-01)
- Never double-book a faculty member (HC-02)
- Never break a lab into non-consecutive slots (HC-03)
- Never eliminate a student's lunch break (HC-04)
- Never exceed a faculty's weekly hour limit (HC-05)
- Always confirm with the user before applying multi-section changes
- Always show a diff (before/after) before finalizing any modification

YOUR RESPONSE FORMAT:
- Be concise but thorough. Use bullet points for slot listings.
- When showing timetable data, format it as a clean text table.
- When a constraint is violated, clearly state: "This change cannot be applied because: [specific reason]"
- When a change is safe, confirm: "✓ Validated — no conflicts detected. Shall I apply this change?"
- Support follow-up questions in context of the ongoing conversation.
- If you're unsure whether a change is permissible, call the constraint check tool first.

TOOL ACCESS — when you need to call a tool, respond with:
<tool_call>{{"name": "tool_name", "arguments": {{"key": "value"}}}}</tool_call>

Available tools:
- query_timetable(section_id, day, period)
- check_constraint_violation(slot_id, proposed_change)
- apply_slot_swap(slot_1_id, slot_2_id, confirmed)
- check_room_availability(room_id, day, period)
- check_faculty_slots(faculty_id, day)
- bulk_update_slots(slot_ids, changes, confirmed)
- generate_modification_report(timetable_id)
- undo_last_change(faculty_id)

Current timetable context: {timetable_id}
Requesting faculty: {faculty_name} | {faculty_id}
Sections taught: {sections_list}
Today's date: {current_date}"""


def build_system_prompt(
    timetable_id: int,
    faculty_name: str,
    faculty_id: str,
    sections_list: list[str],
    current_date: str,
) -> str:
    """Render the ChronoBot system prompt with current context values."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        timetable_id=timetable_id,
        faculty_name=faculty_name,
        faculty_id=faculty_id,
        sections_list=", ".join(sections_list),
        current_date=current_date,
    )
