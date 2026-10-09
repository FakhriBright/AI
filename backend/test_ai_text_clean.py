from app.services.ai.text_clean import clean_llm_text


def test_thousands_separator_nnbsp_removed():
    assert clean_llm_text("Support 4\u202f125.104 dan 4\u00a0138.864") == "Support 4125.104 dan 4138.864"


def test_nbsp_and_nb_hyphen_become_normal():
    out = clean_llm_text("tunggu\u202fprice\u202fbreak\u2011and\u2011hold")
    assert out == "tunggu price break-and-hold"


def test_invisible_removed_and_plain_text_untouched():
    assert clean_llm_text("a\u200bb") == "ab"
    assert clean_llm_text("RR 2 100 lot\nbaris 2") == "RR 2 100 lot\nbaris 2"


def test_internal_field_names_are_humanised():
    out = clean_llm_text("`entry_gate` menolak; cek rr_at_ref dan now_rr, stop_src atr")
    assert "entry_gate" not in out and "rr_at_ref" not in out and "`" not in out
    assert "status entry menolak" in out
