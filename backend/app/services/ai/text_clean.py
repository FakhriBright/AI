"""Clean odd unicode the LLM (notably gpt-oss) sometimes puts in its output.

Narrow no-break spaces and non-breaking hyphens render as cramped words that
cannot wrap in the chat bubble ("tunggupricemenembus...", horizontal scroll).
"""
import re

# "4 125.104" written with a (narrow) no-break space as thousands separator
_THOUSANDS = re.compile(r"(?<=\d)[\u202f\u00a0\u2009\u2007](?=\d{3}(?!\d))")

_SPACE_LIKE = dict.fromkeys(
    map(
        ord,
        "\u202f\u00a0\u2009\u2007\u2008\u200a\u2002\u2003\u2004\u2005\u2006\u3000",
    ),
    " ",
)
_HYPHEN_LIKE = dict.fromkeys(map(ord, "\u2011\u2010\u2212"), "-")
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


# Internal field names the model must not show to the trader.
_INTERNAL_TERMS = {
    "entry_gate": "status entry",
    "can_enter_now": "status entry",
    "rr_at_ref": "RR di level pending",
    "now_rr": "RR masuk sekarang",
    "stop_src": "sumber SL",
    "patterns_for": "pola pendukung",
    "patterns_against": "pola penentang",
    "trigger_dist_atr": "jarak trigger (ATR)",
}
_INTERNAL_RE = re.compile(
    r"`?\b(" + "|".join(sorted(_INTERNAL_TERMS, key=len, reverse=True)) + r")\b`?"
)


def clean_llm_text(text: str) -> str:
    if not text:
        return text
    text = _INTERNAL_RE.sub(lambda m: _INTERNAL_TERMS[m.group(1)], text)
    text = _THOUSANDS.sub("", text)
    text = text.translate(_SPACE_LIKE).translate(_HYPHEN_LIKE).translate(_INVISIBLE)
    return re.sub(r"[ \t]{2,}", " ", text)
