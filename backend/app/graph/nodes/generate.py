from __future__ import annotations
import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from app.graph.state import MigrationState
from app.config import settings

_TARGET_EXT = {
    ("python", "javascript"): "js",
    ("javascript", "python"): "py",
    ("javascript", "typescript"): "ts",
}

_IDIOMATIC = {
    "javascript": "ES2020+, use const/let, arrow functions, async/await, named exports",
    "typescript": "strict TypeScript, explicit types on all params and return values, interfaces over type aliases",
    "python": "Python 3.11+, type hints, dataclasses or Pydantic where appropriate, f-strings",
}


def _get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.1,
    )


def _extract_code(text: str) -> str:
    """Strip markdown code fences if present."""
    match = re.search(r"```(?:\w+)?\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _build_prompt(state: MigrationState) -> str:
    src_lang = state["source_language"]
    tgt_lang = state["target_language"]
    file_path = state["current_file"]
    source = state["current_source"] or ""
    context = state.get("current_context", [])
    idiomatic = _IDIOMATIC.get(tgt_lang, tgt_lang)

    lines = [
        f"You are an expert code migration engineer.",
        f"Convert the {src_lang.upper()} file below into {tgt_lang.upper()}.",
        "",
        "REQUIREMENTS:",
        f"  1. Preserve ALL functionality exactly — same logic, same algorithms.",
        f"  2. Use idiomatic {tgt_lang}: {idiomatic}.",
        f"  3. Convert imports/requires to the target language convention.",
        f"  4. Keep the same class names, function names, and module structure.",
        f"  5. Output ONLY the converted code — no explanations, no markdown fences.",
    ]

    if context:
        lines += [
            "",
            f"ALREADY-CONVERTED DEPENDENCIES (reference these for import paths and types):",
        ]
        for ctx in context:
            lines += [
                f"\n--- {ctx['file_path']} (converted) ---",
                ctx["converted_source"],
            ]

    lines += [
        "",
        f"FILE TO CONVERT: {file_path}",
        "--- SOURCE ---",
        source,
        "--- END SOURCE ---",
        "",
        f"Output the complete {tgt_lang.upper()} file now:",
    ]

    return "\n".join(lines)


def generate_node(state: MigrationState) -> dict:
    """GENERATE: Call Groq to convert the current file."""
    if state.get("error") or not state.get("current_file"):
        return {}

    try:
        llm = _get_llm()
        prompt = _build_prompt(state)
        response = llm.invoke([HumanMessage(content=prompt)])
        converted = _extract_code(response.content)

        return {
            "current_converted": converted,
            "messages": [
                f"[GENERATE] Converted {state['current_file']} "
                f"({len(converted)} chars generated)."
            ],
        }

    except Exception as exc:
        return {
            "current_converted": "",
            "current_validation_errors": [{"line": 0, "message": f"LLM error: {exc}"}],
            "messages": [f"[GENERATE] ERROR for {state['current_file']}: {exc}"],
        }
