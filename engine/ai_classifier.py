"""Pure plumbing for the AI classification batch call.

These helpers have no Streamlit dependency and no I/O, so they live in the engine
and are unit-tested directly rather than inside the page. The page keeps the
``@st.cache_data`` wrapper and the actual OpenAI request; only the deterministic
cache-key construction and the response token-usage extraction live here. This is
the first slice of the page decomposition: the AI module other slices (prompt
builder, response parsing) will grow into.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .text_utils import collapse_ws, shorten
from .constants import LISTING_TOOLS


def make_batch_cache_key(items: List[Dict[str, Any]], model: str, trim_reason: bool) -> Tuple:
    # Cache-key contract: the cached classifier that consumes this key is a pure
    # function of THIS key. Anything that changes a per-item classification result
    # MUST be cooked into the key below (or into `model`): a new
    # classification-affecting toggle, a prompt/schema variant, or an input field.
    # Performance-only knobs (batch_size, concurrency) must NOT go in the key.
    # trim_reason is a schema variant (it removes the reason field), so it is in
    # the key even though it does not change the category itself.
    cooked = []
    for it in items:
        cooked.append(
            (
                str(it.get("row_id", "")),
                collapse_ws(str(it.get("code", ""))),
                collapse_ws(str(it.get("prod_cat", ""))),
                collapse_ws(str(it.get("desc1", ""))),
                collapse_ws(str(it.get("desc2", ""))),
                collapse_ws(str(it.get("supplier_code", ""))).upper(),
                str(it.get("current_pack_units", "")),
                str(it.get("current_size_category", "")),
                str(it.get("listing", "")),
            )
        )
    return (model, bool(trim_reason), tuple(cooked))


def extract_chat_usage(resp) -> Tuple[int, int]:
    """Best-effort (prompt_tokens, completion_tokens) from an OpenAI response.

    Returns (0, 0) if usage is absent or malformed; token accounting is for
    estimates and logging, so a missing figure must never break a run.
    """
    in_t = out_t = 0
    try:
        u = getattr(resp, "usage", None)
        if u is not None:
            in_t = int(getattr(u, "prompt_tokens", 0) or 0)
            out_t = int(getattr(u, "completion_tokens", 0) or 0)
    except Exception:
        pass
    return in_t, out_t


def build_classification_prompt(items_payload: List[Dict[str, Any]]) -> str:
    """Build the batch classification prompt for ``items_payload``.

    The exact wording drives the model's classification and is NOT part of
    the cache key, so it must not drift silently. It is therefore pinned
    byte-for-byte by a golden test (tests/test_ai_prompt.py); change the
    template only by updating that golden deliberately. The trailing JSON is
    the only variable part.
    """
    return f"""
You are an expert in cutting tools, machining tooling, and industrial PPE (personal protective equipment).

Each input item has a "listing" field: "Tools" or "PPE". Use it as a strong prior.

For each item, return:
- product_category: one of [inserts, drills, mills, reamers, holders, screws, accessories, boring_bars, ppe, other]
- tool_class: finer-grained subclass. One of:
  * For inserts: turning_insert, milling_insert, drilling_insert
  * For drills: solid_carbide_drill, indexable_drill, hss_drill, tap
  * For mills: solid_end_mill, shell_mill, face_mill, thread_mill
  * For reamers: reamer
  * For boring_bars: boring_bar
  * For holders: turning_holder, milling_holder, collet
  * For screws: screw
  * For accessories: wrench, abrasive_disc, abrasive_belt, grinding_wheel, accessory
  * For ppe: ppe
  * Fallback: other
- size_category: exactly one of [S, M, L, XL, XXL, XXLS, XLS]
- pack_units: integer, usually 1 or 10 (or null if uncertain)
- confidence: "high" (clear evidence in description/code), "medium" (inferred from supplier+context), or "low" (guess)
- reason: ONE short sentence (max 15 words) pointing at the specific field that led to the classification. Examples:
  * "ISO insert code CNMG in description"
  * "Seco WS-grade carbide insert code"
  * "Description starts with FO (Foret = drill in French)"
  * "Supplier Guhring specializes in carbide drills"
  * "No clear category indicators in description or code"

Listing rule (CRITICAL):
- If listing == "PPE", strongly prefer product_category = ppe. Only fall back to another category if the item is clearly NOT PPE (e.g., a cleaning chemical or a misfiled tool).
- If listing == "Tools", never output product_category = ppe.

Insert rule (CRITICAL, Tools only):
- If listing == "Tools" and the text contains insert-like wording such as insert, wendeplatte, wendeschneidplatte, plaquette, or ISO insert codes, classify as inserts even if the same text also contains drilling, milling, turning, bohrer, fraesen, drehen, etc.
- Examples: "Insert for drilling" -> inserts | "Wendeplatte : Bohrer" -> inserts

Rules for pack_units if missing/incorrect:
- inserts -> 10
- drills, mills, reamers -> 1
- holders, screws, accessories, boring_bars -> 1
- ppe -> 1 (items are usually counted individually; a box of gloves should still be pack=1 unless clearly sold as a pack)

Important insert hints (Tools only):
- ISO-style insert codes: CCMT, CNMG, CNMM, CNMA, CNGA, DCGT, DNMG, DNMM, DNMA, DNGA, VNMG, VCGT, VBMT, RCMT, SPGT, TCMT, TPKN, APKT, ADKT, LNMT, LNHT, TCKT, ANCX, WXCU, QPMT
- Inserts default: size_category=S, pack_units=10

Supplier brand hints (Tools only):
The supplier_code field may contain a cutting-tool manufacturer name. Common brands and what they typically make:
- Seco, Sandvik, Iscar, Mitsubishi, Walter, Kennametal, Sumitomo, Korloy, Tungaloy, Widia: these are major cutting-tool brands. They produce inserts (most volume), drills, mills, reamers, boring bars, and toolholders.
- Seco proprietary patterns often include grade suffixes like -TP1500, -TS2050, -CP500, -F40M, -MK1500, or standalone codes like WS-grade, MM-grade, MS-grade.
- Iscar uses IC8xxx / IC9xxx grade suffixes (IC8250, IC9350, IC907, etc.).
- Sandvik uses long numeric codes like 5322-425-04, 5412-028-041, 170.3-852.

When the supplier_code is one of these brands AND the description has no clear category word (no drill/bohrer/foret/fraise/mill/holder/halter/etc.) AND no ISO insert code is present, the item is MOST LIKELY an insert (inserts are by far the highest-volume product line at all these brands). Default to product_category=inserts with pack_units=10 in that case, unless the description explicitly says otherwise.

However, ALWAYS trust explicit category words in the description over the supplier hint:
- "Sandvik CoroDrill ..." -> drills (CoroDrill is Sandvik's drill line; the word "drill" wins)
- "Seco Jabro endmill ..." -> mills (endmill wins)
- "Iscar HELIDO holder ..." -> holders (holder wins)
- "Sandvik insert ..." or "Seco TS2050" with no other context -> inserts

PPE size hints:
- earplugs, safety glasses, masks, gloves -> S
- safety boots, helmets/hard hats -> XL
- coveralls, full-body protection -> XXL
- unknown PPE -> M

Multilingual category hints:
- screws: screw, schraube, schrauben, vis, vite, viti, tornillo, tornillos, parafuso, parafusos
- accessories: accessory, accessories, access, zubehör, zubehoer, spare, ersatz, clamp, klemm
- ppe: glove/gant/handschuh, goggle/lunette/brille, earplug/bouchon/ohrstöpsel, mask/masque/maske, boot/chaussure/stiefel, helmet/casque/helm/casco, coverall/combinaison

If truly uncertain:
- product_category=other (Tools) or ppe (PPE)
- size_category=L (Tools) or M (PPE)
- pack_units=null

Return exactly one result per input item, preserving the exact row_id.

Input items JSON:
{json.dumps(items_payload, ensure_ascii=False)}
""".strip()


def build_classification_batches(work, capped_rows, *, batch_size, model,
                                 trim_reason, max_desc_chars):
    """Split the rows that need AI into batches and build each batch's payload.

    Given the planning frame ``work`` and the ordered list of row indices that
    require an AI call (``capped_rows``), this returns one plan dict per batch:

      {"b": <batch ordinal>, "batch_idx": [row indices],
       "cache_key": <deterministic key for the cached classifier>,
       "n_items": <count>}

    The per-item payload mirrors exactly what the model is asked to classify
    (code, product category, two descriptions, supplier code, current pack-units
    and size category, listing). ``max_desc_chars`` bounds each description and
    ``model`` / ``trim_reason`` feed the cache key. This is pure: it reads the
    frame and returns plans; it makes no model call and touches no Streamlit. The
    caller runs the batches (today in parallel with a progress bar) and merges the
    results back.
    """
    import math

    batch_plans = []
    total_batches = math.ceil(len(capped_rows) / int(batch_size))
    for b in range(total_batches):
        start = b * int(batch_size)
        end = min(len(capped_rows), (b + 1) * int(batch_size))
        batch_idx = capped_rows[start:end]

        items = []
        for idx in batch_idx:
            row = work.loc[idx]
            items.append(
                {
                    "row_id": str(idx),
                    "code": collapse_ws(str(row.get("Code", ""))),
                    "prod_cat": collapse_ws(str(row.get("ProductCategory", ""))),
                    "desc1": shorten(row.get("Description", ""), max_desc_chars),
                    "desc2": shorten(row.get("Description_2", ""), max_desc_chars),
                    "supplier_code": collapse_ws(str(row.get("SupplierCode", ""))).upper(),
                    "current_pack_units": str(int(float(row.get("PackUnits", 1.0)))),
                    "current_size_category": collapse_ws(str(row.get("SizeCategory", ""))).upper(),
                    "listing": str(row.get("Listing", LISTING_TOOLS)),
                }
            )

        cache_key = make_batch_cache_key(items, model, trim_reason)
        batch_plans.append(
            {
                "b": b,
                "batch_idx": batch_idx,
                "cache_key": cache_key,
                "n_items": len(batch_idx),
            }
        )
    return batch_plans


@dataclass
class AIRunDiagnostics:
    """Counters and token usage accumulated while running the AI classification.

    The classification driver fires batches in parallel and, as each future
    completes, folds its outcome in here: token usage, per-batch duration, error
    or missing-response notes, and the batches/items processed. This keeps the
    bookkeeping in one structured place instead of a handful of loose variables,
    and gives the surrounding code derived figures (total tokens, average batch
    duration, cost at a given price) without re-deriving them each time. It holds
    no Streamlit state; the caller owns the progress bar and feeds results in.
    """

    batches_run: int = 0
    items_run: int = 0
    batches_failed: int = 0
    missing_responses: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    errors: List[str] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)

    def record_crash(self, batch_label: int, total_batches: int, exc: BaseException) -> None:
        """Record a worker future that raised. ``batch_label`` is 1-based."""
        self.errors.append(
            f"Batch {batch_label}/{total_batches} crashed: {type(exc).__name__}: {exc}"
        )
        self.batches_failed += 1

    def record_batch(self, res: Dict[str, Any], total_batches: int) -> None:
        """Fold one completed batch result dict into the totals."""
        self.in_tokens += int(res["in_tok"])
        self.out_tokens += int(res["out_tok"])
        self.durations.append(res["duration"])
        if res["err"]:
            self.batches_failed += 1
            self.errors.append(
                f"Batch {res['b']+1}/{total_batches} ({res['n_items']} items): {res['err']}"
            )
        elif res["missing"] > 0:
            self.missing_responses += res["missing"]
        self.batches_run += 1
        self.items_run += res["n_items"]

    @property
    def total_tokens(self) -> int:
        return self.in_tokens + self.out_tokens

    @property
    def avg_duration(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 0.0

    def cost(self, price_in_per_1m: float, price_out_per_1m: float) -> float:
        """Estimated dollar cost given per-million-token input/output prices."""
        return (self.in_tokens / 1_000_000) * price_in_per_1m + (
            self.out_tokens / 1_000_000
        ) * price_out_per_1m
