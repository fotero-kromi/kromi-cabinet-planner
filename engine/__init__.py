"""kromi_app.engine — cabinet-planning engine.

Pure-Python math and classification logic, decoupled from the Streamlit UI.
Every public function here is side-effect-free (no Streamlit calls, no global
state, no implicit I/O), which makes the engine independently unit-testable;
see the ``tests/`` package for the suite.

The Streamlit pages import what they need from this package via the re-exports
below. A handful of functions accept an explicit ``base_dir`` or runtime factor
argument so the engine carries no global state; the pages bind those through
thin wrappers that supply the current runtime values.
"""

# Public API re-exports, grouped by module and alphabetized within each group.

# --- Domain constants: machine specs, taxonomies, keyword tables ---
# --- Cabinet sizing math + bidirectional rebalancer ---
# Pure but parametrized: the single-spiral overfill factor and carousel
# reserve factor (both adjustable in the UI sidebar) are passed in as
# arguments rather than read from globals, so the engine stays stateless.
from .cabinet_math import (
    _partition_supply_points_lpt,
    _replicate_across_supply_points,
    apply_bulk_routing,
    apply_capacity_buffer,
    assign_supply_points,
    compute_carousel_needs,
    compute_locker_needs,
    decide_cabinet_type,
    decide_spiral_capacity,
)
from .cabinet_math import (
    compute_helix_needs as _engine_compute_helix_needs,
)
from .cabinet_math import (
    # These four accept overfill_factor / carousel_reserve_factor (with
    # defaults); the pages wrap them to pass the current sidebar values.
    compute_helix_spirals_needed as _engine_compute_helix_spirals_needed,
)
from .cabinet_math import (
    compute_plan_for_subset as _engine_compute_plan_for_subset,
)
from .cabinet_math import (
    rebalance_cabinets as _engine_rebalance_cabinets,
)

# --- Product classification (the largest module) ---
# Heuristic classifier path, ISO insert-code detection, French shorthand,
# supplier-code patterns, ToolClass derivation, and bulk-family detection.
# All pure; depend on engine.constants and engine.text_utils.
from .classification import (
    _check_supplier_code_pattern,
    _check_supplier_specialty,
    _kw_matches,
    _shorthand_matches,
    _supplier_brand_matches,
    classify_with_evidence,
    derive_tool_class,
    detect_item_family,
    first_valid_product_category,
    heuristic_pack_units,
    heuristic_pack_units_from_text,
    heuristic_product_category,
    heuristic_product_category_with_listing,
    heuristic_size_category,
    is_insert_text,
    is_ppe_text,
    is_weak_category,
    looks_like_insert_code,
    normalize_product_category,
)
from .constants import (
    ACCESSORY_KEYWORDS,
    # Override schema
    BORING_BAR_KEYWORDS,
    BULK_ALWAYS_FAMILIES,
    CABINET_TYPES_VALID,
    CAROUSEL_RESERVE_FACTOR,
    CAROUSEL_SLOTS_PER_CAB,
    DAYS_PER_MONTH,
    DISPOSABLE_PPE_FAMILIES,
    # Keyword lists used by classifier
    DRILL_KEYWORDS,
    DRILL_SHORTHAND_FR,
    GRINDING_SHORTHAND_FR,
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR,
    # Machine specs
    HELIX_SPIRALS_PER_CAB,
    HOLDER_KEYWORDS,
    INSERT_KEYWORDS,
    LISTING_PPE,
    # Listing labels
    LISTING_TOOLS,
    LISTING_VALID,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
    MILL_KEYWORDS,
    MILL_SHORTHAND_FR,
    OVERRIDE_COLUMNS,
    OVERRIDE_SCHEMA_VERSION,
    OVERRIDE_VALID_CABINETS,
    OVERRIDE_VALID_SIZES,
    OVERRIDE_VALID_VEND,
    # Misc
    PACK_HINT_PATTERNS,
    PACK_MONTH_EPS,
    # Category taxonomies
    PC_VALID,
    PPE_KEYWORDS,
    REAMER_KEYWORDS,
    REAMER_SHORTHAND_FR,
    SCREW_KEYWORDS,
    SIZE_VALID,
    # Slide / distribution buckets
    SLIDE_BUCKET_ORDER,
    SLIDE_DISTRIBUTION_BUCKETS,
    # SP modes
    SP_MODE_PARTITION,
    SP_MODE_REPLICATE,
    SP_MODE_VALID,
    # Supplier pattern tables
    SUPPLIER_CODE_PATTERNS,
    SUPPLIER_SPECIALTY,
    TOOL_CLASS_VALID,
    TOOLCLASS_FROM_PRODUCT_CATEGORY,
    TOOLCLASS_TO_BUCKET,
    TOOLCLASS_TO_PRODUCT_CATEGORY,
)

# --- Per-supply-point distribution / occupation summaries ---
# All pure; depend only on engine.constants.
from .distribution import (
    _slide_bucket_for_category,
    build_per_sp_cabinet_occupation,
    build_per_sp_distribution,
    build_per_sp_subclass_breakdown,
    build_per_sp_summary,
)

# --- Technician overrides (validators, loader/saver, applier) ---
# load_overrides / save_overrides / overrides_folder take an explicit base_dir
# (the engine holds no global state); the pages wrap them to supply the
# overrides directory and an error callback so call sites stay unchanged.
from .overrides import (
    _parse_pack_override,
    _safe_scope_component,
    _valid_cabinet_type,
    _valid_category,
    _valid_size,
    _valid_vend_mode,
    apply_overrides,
)
from .overrides import (
    # These three take base_dir; the page shims them, see below.
    load_overrides as _engine_load_overrides,
)
from .overrides import (
    overrides_folder as _engine_overrides_folder,
)
from .overrides import (
    save_overrides as _engine_save_overrides,
)

# --- Planning-base preprocessing (year filter + dedup) ---
# Pure; depends on engine.text_utils + engine.classification.
from .preprocessing import (
    prepare_planning_base,
)

# --- Text + numeric parsing helpers ---
from .text_utils import (
    _fmt_seconds,
    _normalize_size_code,
    _strip_json_code_fence,
    clean_text_cell,
    collapse_ws,
    contains_any_keyword,
    first_nonempty,
    first_positive_number,
    first_valid_size,
    guess_column,
    norm,
    parse_number_series,
    parse_year_series,
    shorten,
)
