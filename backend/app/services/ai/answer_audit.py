"""Post-hoc grounding audit of the model's answer (observability only).

Every decimal number the model quotes should come from the structured context
it was given. Numbers that do not appear there are likely fabricated or
re-computed by the model (which it is told not to do). The audit never edits
the answer; it only reports, so problems become visible in the logs.
"""
import json
import re

_NUMBER = re.compile(r"(?<![\w.])-?\d+\.\d{2,}(?![\w])")


def _tolerance(value: float) -> float:
    # the model may round 4173.348 -> 4173.35 (or 1.12234 -> 1.1223)
    return 0.011 if abs(value) >= 100 else 0.0011 if abs(value) >= 1 else 0.00011


def audit_answer(text: str, context: dict) -> dict:
    """Return {'checked': n, 'ungrounded': [numbers not found in context]}."""
    if not text:
        return {"checked": 0, "ungrounded": []}

    known = [
        float(m.group(0))
        for m in _NUMBER.finditer(json.dumps(context, ensure_ascii=False, default=str))
    ]
    quoted = [float(m.group(0)) for m in _NUMBER.finditer(text)]

    ungrounded: list[float] = []
    for value in quoted:
        tol = _tolerance(value)
        if not any(abs(value - k) <= tol for k in known) and value not in ungrounded:
            ungrounded.append(value)
    return {"checked": len(quoted), "ungrounded": ungrounded}
