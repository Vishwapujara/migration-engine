from __future__ import annotations
import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from app.graph.state import MigrationState
from app.config import settings


def _get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.15,
    )


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:\w+)?\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _build_correction_prompt(state: MigrationState) -> str:
    tgt_lang = state["target_language"]
    file_path = state["current_file"]
    converted = state.get("current_converted") or ""
    errors = state.get("current_validation_errors", [])
    attempt = state.get("self_correction_attempts", 0) + 1

    error_lines = "\n".join(
        f"  Line {e.get('line', '?')}: {e.get('message', str(e))}"
        for e in errors[:10]  # Cap at 10 to stay within token limits
    )

    return "\n".join([
        f"The {tgt_lang.upper()} code you generated for {file_path} has validation errors.",
        f"This is correction attempt {attempt} of {settings.max_self_correction_retries}.",
        "",
        "VALIDATION ERRORS:",
        error_lines,
        "",
        "CURRENT (BROKEN) CODE:",
        converted,
        "",
        "Fix ONLY the errors listed above. Keep all other logic identical.",
        "Output ONLY the corrected code — no explanations, no markdown fences.",
    ])


def self_correct_node(state: MigrationState) -> dict:
    """SELF_CORRECT: Re-prompt Groq with validation errors; increment attempt counter."""
    if not state.get("current_file"):
        return {}

    attempt = state.get("self_correction_attempts", 0)

    try:
        llm = _get_llm()
        prompt = _build_correction_prompt(state)
        response = llm.invoke([HumanMessage(content=prompt)])
        corrected = _extract_code(response.content)

        return {
            "current_converted": corrected,
            "self_correction_attempts": attempt + 1,
            "messages": [
                f"[SELF_CORRECT] {state['current_file']}: attempt {attempt + 1} — "
                f"regenerated {len(corrected)} chars."
            ],
        }

    except Exception as exc:
        return {
            "self_correction_attempts": attempt + 1,
            "messages": [f"[SELF_CORRECT] ERROR for {state['current_file']}: {exc}"],
        }
