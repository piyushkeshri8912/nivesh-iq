import json
import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def extract_text(result: Any, strip: bool = True) -> str:
    """
    Safely extract text content from LangChain Chat model responses.
    """
    try:
        content = getattr(result, "content", result)
        if isinstance(content, list):
            val = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            return val.strip() if strip else val
        if isinstance(content, dict):
            val = content.get("text", str(content))
            return val.strip() if strip else val
        val = str(content)
        return val.strip() if strip else val
    except Exception as e:
        logger.error(f"Failed to extract text from model result: {e}")
        return ""


def clean_and_parse_json(raw_text: str) -> Any:
    """
    Safely clean and deserialize JSON content from model raw texts.
    Strips markdown formatting blocks (e.g. ```json ... ```) if present.
    If standard parsing fails, falls back to a robust scanning extractor.
    """
    cleaned = raw_text.strip()
    if not cleaned:
        return {}

    # Try parsing whole text first
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    # Find the bounds of the first JSON array or object
    first_bracket = cleaned.find('[')
    last_bracket = cleaned.rfind(']')
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = cleaned[first_bracket:last_bracket+1]
        try:
            return json.loads(candidate, strict=False)
        except Exception:
            pass

    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace+1]
        try:
            return json.loads(candidate, strict=False)
        except Exception:
            pass

    # Strip markdown wrapper and try again
    if cleaned.startswith("```"):
        cleaned_stripped = re.sub(r"^```[a-zA-Z]*\n|```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned_stripped, strict=False)
        except Exception:
            pass

    # Fallback parsing for common schema keys
    if first_brace != -1:
        extracted = {}
        # Helper to extract a string field
        def scan_string_field(field_name: str) -> str:
            pattern = rf'"{field_name}"\s*:\s*"'
            match = re.search(pattern, cleaned)
            if not match:
                return ""
            start_idx = match.end()
            chars = []
            escaped = False
            for i in range(start_idx, len(cleaned)):
                char = cleaned[i]
                if escaped:
                    if char == 'n': chars.append('\n')
                    elif char == 't': chars.append('\t')
                    elif char == 'r': chars.append('\r')
                    elif char == 'b': chars.append('\b')
                    elif char == 'f': chars.append('\f')
                    elif char == '"': chars.append('"')
                    elif char == '\\': chars.append('\\')
                    else: chars.append('\\' + char)
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    break
                else:
                    chars.append(char)
            return "".join(chars)

        # Helper to extract a list of strings field
        def scan_list_field(field_name: str) -> list[str]:
            pattern = rf'"{field_name}"\s*:\s*\['
            match = re.search(pattern, cleaned)
            if not match:
                return []
            start_idx = match.end()
            items = []
            current_str = []
            in_string = False
            escaped = False
            for i in range(start_idx, len(cleaned)):
                char = cleaned[i]
                if in_string:
                    if escaped:
                        if char == 'n': current_str.append('\n')
                        elif char == 't': current_str.append('\t')
                        elif char == 'r': current_str.append('\r')
                        elif char == 'b': current_str.append('\b')
                        elif char == 'f': current_str.append('\f')
                        elif char == '"': current_str.append('"')
                        elif char == '\\': current_str.append('\\')
                        else: current_str.append('\\' + char)
                        escaped = False
                    elif char == '\\':
                        escaped = True
                    elif char == '"':
                        in_string = False
                        items.append("".join(current_str))
                        current_str = []
                    else:
                        current_str.append(char)
                else:
                    if char == '"':
                        in_string = True
                    elif char == ']':
                        break
            return items

        ans = scan_string_field("answer")
        cav = scan_string_field("caveat")
        ev = scan_list_field("evidence")
        ns = scan_list_field("next_steps")
        
        if ans or cav:
            extracted["answer"] = ans
            extracted["caveat"] = cav
            extracted["evidence"] = ev
            extracted["next_steps"] = ns
            extracted["plan_draft"] = {
                "intent": "DIRECT",
                "summary": "Fallback parsed fields",
                "risk_flags": []
            }
            return extracted

    if cleaned:
        return {
            "answer": cleaned,
            "caveat": "This is for informational purposes only.",
            "evidence": [],
            "next_steps": [],
            "plan_draft": {
                "intent": "DIRECT",
                "summary": "Fallback to raw text",
                "risk_flags": []
            }
        }

    return {}


def extract_token_usage(result: Any) -> Dict[str, int]:
    """
    Safely extract token usage statistics from a Chat model result.
    Checks multiple possible locations since different LLM providers
    (Vertex AI, OpenAI, Anthropic) store usage in different attributes.
    """
    usage: Dict[str, Any] = {}

    # Path 1: response_metadata.usage_metadata (OpenAI-style)
    rm = getattr(result, "response_metadata", None)
    if rm is not None:
        if isinstance(rm, dict):
            usage = rm.get("usage_metadata") or rm.get("usage") or {}
        else:
            # response_metadata might be an object with attributes
            usage = getattr(rm, "usage_metadata", None) or getattr(rm, "usage", None) or {}

    # Path 2: usage_metadata directly on the result (some LangChain implementations)
    if not usage:
        usage = getattr(result, "usage_metadata", None) or {}

    # Path 3: token_usage directly on the result (older LangChain style)
    if not usage:
        usage = getattr(result, "token_usage", None) or {}

    # Path 4: if result itself is a dict
    if not usage and isinstance(result, dict):
        usage = result.get("usage_metadata") or result.get("token_usage") or {}

    # Path 5: search all attributes for anything containing "usage" or "token"
    if not usage:
        for attr_name in dir(result):
            if attr_name.startswith("_"):
                continue
            if "usage" in attr_name.lower() or "token" in attr_name.lower():
                attr_val = getattr(result, attr_name, None)
                if isinstance(attr_val, dict) and attr_val:
                    usage = attr_val
                    logger.debug(f"Found usage in attribute '{attr_name}': {usage}")
                    break
                elif isinstance(attr_val, int) and attr_val > 0:
                    # Single integer token count
                    usage = {"total_tokens": attr_val}
                    break

    if not usage:
        available = [a for a in dir(result) if not a.startswith("_")]
        logger.debug(f"No token usage metadata found. Result type: {type(result).__name__}, Available attrs: {available}")
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    prompt = (
        usage.get("prompt_tokens")
        or usage.get("prompt_token_count")
        or usage.get("input_tokens")
        or usage.get("input_token_count")
        or 0
    )
    completion = (
        usage.get("completion_tokens")
        or usage.get("candidates_tokens")
        or usage.get("candidates_token_count")
        or usage.get("output_tokens")
        or usage.get("output_token_count")
        or 0
    )
    total = (
        usage.get("total_tokens")
        or usage.get("total_token_count")
        or usage.get("total_count")
        or (prompt + completion)
    )

    result_dict = {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total)
    }
    logger.debug(f"Extracted token usage: {result_dict}")
    return result_dict
