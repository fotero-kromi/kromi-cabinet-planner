"""Tests for the pure AI plumbing extracted from the page (v33.77)."""

from engine.ai_classifier import make_batch_cache_key, extract_chat_usage


def _items():
    return [
        {"row_id": "1", "code": "CNMG 120408", "prod_cat": "inserts",
         "desc1": "turning insert", "desc2": "", "supplier_code": "seco",
         "current_pack_units": "10", "current_size_category": "M", "listing": "Tools"},
        {"row_id": "2", "code": "FORET 6.0", "prod_cat": "drills",
         "desc1": "carbide drill", "desc2": "", "supplier_code": "guhring",
         "current_pack_units": "1", "current_size_category": "S", "listing": "Tools"},
    ]


def test_cache_key_is_deterministic():
    assert make_batch_cache_key(_items(), "gpt-x", False) == \
        make_batch_cache_key(_items(), "gpt-x", False)


def test_trim_reason_changes_the_key():
    full = make_batch_cache_key(_items(), "gpt-x", False)
    trim = make_batch_cache_key(_items(), "gpt-x", True)
    assert full != trim
    # the trim flag rides in the key as a bool, distinct from the model/items
    assert full[1] is False and trim[1] is True


def test_model_change_changes_the_key():
    assert make_batch_cache_key(_items(), "gpt-a", False) != \
        make_batch_cache_key(_items(), "gpt-b", False)


def test_item_change_changes_the_key():
    other = _items()
    other[0]["code"] = "DNMG 150608"
    assert make_batch_cache_key(other, "gpt-x", False) != \
        make_batch_cache_key(_items(), "gpt-x", False)


def test_supplier_code_is_case_folded_in_key():
    a = _items(); a[0]["supplier_code"] = "Seco"
    b = _items(); b[0]["supplier_code"] = "SECO"
    assert make_batch_cache_key(a, "gpt-x", False) == \
        make_batch_cache_key(b, "gpt-x", False)


def test_whitespace_is_collapsed_in_key():
    a = _items(); a[0]["desc1"] = "turning   insert"
    b = _items(); b[0]["desc1"] = "turning insert"
    assert make_batch_cache_key(a, "gpt-x", False) == \
        make_batch_cache_key(b, "gpt-x", False)


class _Usage:
    def __init__(self, p, c):
        self.prompt_tokens = p
        self.completion_tokens = c


class _Resp:
    def __init__(self, usage):
        self.usage = usage


def test_extract_usage_reads_tokens():
    assert extract_chat_usage(_Resp(_Usage(120, 45))) == (120, 45)


def test_extract_usage_missing_is_zero():
    assert extract_chat_usage(_Resp(None)) == (0, 0)
    assert extract_chat_usage(object()) == (0, 0)
