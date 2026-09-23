"""kromi_app.engine.classification_tables — split out of constants.py (v34.35).

The deterministic classification taxonomy: valid categories and sizes,
the keyword tables per tool family, supplier patterns, pack hints, and
the toolclass and presentation-bucket maps.
"""

__all__ = ['ACCESSORY_KEYWORDS', 'BORING_BAR_KEYWORDS', 'BROACH_KEYWORDS', 'BRUSH_KEYWORDS', 'BULK_ALWAYS_FAMILIES', 'CENTER_POINT_KEYWORDS', 'COUNTERBORE_KEYWORDS', 'DISPOSABLE_PPE_FAMILIES', 'DRILL_KEYWORDS', 'DRILL_SHORTHAND_FR', 'FORM_STEEL_KEYWORDS', 'GEAR_CUTTING_KEYWORDS', 'GRINDING_SHORTHAND_FR', 'GRINDING_TOOL_KEYWORDS', 'HOLDER_KEYWORDS', 'HONING_TOOL_KEYWORDS', 'INSERT_KEYWORDS', 'KEYWORD_TO_TOOLCLASS', 'MILL_KEYWORDS', 'MILL_SHORTHAND_FR', 'PACK_HINT_PATTERNS', 'PC_VALID', 'PPE_KEYWORDS', 'PUNCHING_KEYWORDS', 'REAMER_KEYWORDS', 'REAMER_SHORTHAND_FR', 'SCREW_KEYWORDS', 'SIZE_VALID', 'SLIDE_BUCKET_ORDER', 'SLIDE_DISTRIBUTION_BUCKETS', 'SUPPLIER_CODE_PATTERNS', 'SUPPLIER_SPECIALTY', 'TAP_KEYWORDS', 'THREAD_DIE_KEYWORDS', 'THREAD_MILL_KEYWORDS', 'THRESHOLD_CATEGORIES', 'TOOLCLASS_FROM_PRODUCT_CATEGORY', 'TOOLCLASS_TO_BUCKET', 'TOOLCLASS_TO_PRODUCT_CATEGORY', 'TOOL_CLASS_VALID', 'TOOL_HOLDER_KEYWORDS', 'WELDING_KEYWORDS']

# HELPERS
SIZE_VALID = {"S", "M", "L", "XL", "XXL", "XXLS", "XLS"}

PC_VALID = {
    # Existing categories (kept as-is)
    "inserts",  # Kromi L1: Wendeschneidplatten
    "drills",  # Kromi L1: Bohrer
    "mills",  # Kromi L1: Fräser
    "reamers",  # Kromi L1: Reibahlen
    "holders",  # Kromi L1: Halter (insert holders: turning/milling/drilling)
    "screws",  # Engine-specific; non-Kromi
    "accessories",  # Kromi L1: Zubehör
    "boring_bars",  # Engine-specific; triggers only on explicit "Bohrstange"/"boring bar"
    "ppe",  # Engine-specific
    "other",  # Kromi L1: Weitere
    # Full Kromi L1 alignment
    "taps",  # Kromi L1: Gewindewerkzeuge → Gewindebohrer / Gewindeformer
    "thread_mills",  # Kromi L1: Gewindewerkzeuge → Gewindefräser / Gewindebohrfräser
    "thread_dies",  # Kromi L1: Gewindewerkzeuge → Schneideisen / Gewinderoller
    "counterbores",  # Kromi L1: Senker (Rückwärtssenker, Kegelsenker, Flachsenker, etc.)
    "tool_holders",  # Kromi L1: Werkzeugaufnahme (HSK, SK, VDI, Capto, ABS, MASBT, BMT, MK)
    "grinding_tools",  # Kromi L1: Schleifkörper (Schleifscheibe, Honstein, Abrichter, etc.)
    "brushes",  # Kromi L1: Bürste
    "broaches",  # Kromi L1: Räumwerkzeug
    "honing_tools",  # Kromi L1: Honahlen
    "gear_cutting",  # Kromi L1: Verzahnungswerkzeug
    "center_points",  # Kromi L1: Zentrierspitzen
    "welding",  # Kromi L1: Schweißen
    "punching",  # Kromi L1: Stanzwerkzeug
    "form_steel",  # Kromi L1: Formstahl
}

# Tool-class buckets (Kromi L1 ProductCategory) offered as optional per-class
# KTC/Kanban thresholds in the UI. Inserts lead (the established special case);
# screws/accessories are included for completeness even though the
# force-screws/accessories rule usually pins them to Kanban regardless. A row
# whose category is not in this list uses the standard threshold.
THRESHOLD_CATEGORIES: list[str] = [
    "inserts",
    "drills",
    "mills",
    "taps",
    "thread_mills",
    "thread_dies",
    "reamers",
    "boring_bars",
    "holders",
    "tool_holders",
    "accessories",
    "screws",
]

# ToolClass is a finer-grained subclassification. Optional metadata: not every
# row will have a ToolClass; only those where heuristic or AI can identify
# the specific tool subtype. Cabinet sizing math still uses ProductCategory
# as the routing axis. ToolClass is surfaced in the Technician Review panel
# and exported to the Excel result for downstream analysis.
TOOL_CLASS_VALID = {
    # inserts subclasses (Kromi L2: WSP Bohren / Drehen / Fräsen / Stechen / Gewinde / etc.)
    "turning_insert",
    "milling_insert",
    "drilling_insert",
    "grooving_insert",
    "threading_insert",
    "reaming_insert",
    # drills subclasses (Kromi L2: Spiralbohrer, Stufenbohrer, NC-Anbohrer, etc.)
    "solid_carbide_drill",
    "indexable_drill",
    "hss_drill",
    "spiral_drill",
    "step_drill",
    "nc_drill",
    "center_drill",
    "deep_hole_drill",
    "core_drill",
    "pilot_drill",
    # taps (Kromi L2: Gewindebohrer HSS/HSS-E/VHM/PM) — split out of "drills"
    "tap",
    "tap_carbide",
    "tap_hss",
    # thread mills (Kromi L2: Gewindefräser, Gewindeformer, Gewindebohrfräser)
    "thread_mill",
    "thread_former",
    "thread_hole_cutter",
    # thread dies (Kromi L2: Schneideisen, Gewinderoller)
    "threading_die",
    "thread_roller",
    # mills subclasses (Kromi L2: Schaftfräser, Walzenstirnfräser, Scheibenfräser, etc.)
    "solid_end_mill",
    "shell_mill",
    "face_mill",
    "disc_mill",
    "burr",
    "saw_blade",
    "form_mill",
    "ball_track_mill",
    "radius_mill",
    "t_slot_mill",
    # reamers (Kromi L2: einstufig / mehrstufig)
    "reamer",
    "multi_stage_reamer",
    # counterbores (Kromi L2: Kegelsenker, Flachsenker, Rückwärtssenker, Stufensenker)
    "countersink",
    "flat_countersink",
    "back_countersink",
    "step_countersink",
    "deburring_fork",
    # boring
    "boring_bar",
    # holders (insert holders) subclasses (Kromi L2: Drehen / Fräsen / Bohren / Reiben)
    "turning_holder",
    "milling_holder",
    "drilling_holder",
    "boring_holder",
    "reaming_holder",
    "grooving_holder",
    "collet",
    # tool_holders (machine-spindle interfaces) — Kromi L2: HSK / SK / VDI / Capto / ABS / etc.
    "hsk_holder",
    "sk_holder",
    "vdi_holder",
    "capto_holder",
    "abs_holder",
    "masbt_holder",
    "bmt_holder",
    "mk_holder",
    "varilock_holder",
    "varia_holder",
    "km_holder",
    # grinding tools (Kromi L2: Schleifscheibe, Honstein, Abrichter, etc.)
    "grinding_wheel",
    "grinding_pin",
    "honing_stone",
    "dressing_tool",
    "cutting_disc",
    "flap_wheel",
    "abrasive_belt",
    "abrasive_disc",
    # other tool families
    "brush",
    "broach",
    "honing_reamer",
    "gear_cutter",
    "center_point",
    "welding_consumable",
    "punch_die",
    "form_steel",
    # screws & accessories
    "screw",
    "wrench",
    "accessory",
    # ppe and fallback
    "ppe",
    "other",
}

# Mapping from ToolClass back to ProductCategory. Used when ToolClass was
# determined but ProductCategory wasn't set yet (rare but possible).
TOOLCLASS_TO_PRODUCT_CATEGORY = {
    # inserts
    "turning_insert": "inserts",
    "milling_insert": "inserts",
    "drilling_insert": "inserts",
    "grooving_insert": "inserts",
    "threading_insert": "inserts",
    "reaming_insert": "inserts",
    # drills
    "solid_carbide_drill": "drills",
    "indexable_drill": "drills",
    "hss_drill": "drills",
    "spiral_drill": "drills",
    "step_drill": "drills",
    "nc_drill": "drills",
    "center_drill": "drills",
    "deep_hole_drill": "drills",
    "core_drill": "drills",
    "pilot_drill": "drills",
    # taps — NOW correctly map to taps PC (was: accessories)
    "tap": "taps",
    "tap_carbide": "taps",
    "tap_hss": "taps",
    # thread mills
    "thread_mill": "thread_mills",
    "thread_former": "thread_mills",
    "thread_hole_cutter": "thread_mills",
    # thread dies
    "threading_die": "thread_dies",
    "thread_roller": "thread_dies",
    # mills
    "solid_end_mill": "mills",
    "shell_mill": "mills",
    "face_mill": "mills",
    "disc_mill": "mills",
    "burr": "mills",
    "saw_blade": "mills",
    "form_mill": "mills",
    "ball_track_mill": "mills",
    "radius_mill": "mills",
    "t_slot_mill": "mills",
    # reamers
    "reamer": "reamers",
    "multi_stage_reamer": "reamers",
    # counterbores
    "countersink": "counterbores",
    "flat_countersink": "counterbores",
    "back_countersink": "counterbores",
    "step_countersink": "counterbores",
    "deburring_fork": "counterbores",
    # boring
    "boring_bar": "boring_bars",
    # insert holders (Halter)
    "turning_holder": "holders",
    "milling_holder": "holders",
    "drilling_holder": "holders",
    "boring_holder": "holders",
    "reaming_holder": "holders",
    "grooving_holder": "holders",
    "collet": "holders",
    # tool holders (Werkzeugaufnahme — machine-spindle interfaces)
    "hsk_holder": "tool_holders",
    "sk_holder": "tool_holders",
    "vdi_holder": "tool_holders",
    "capto_holder": "tool_holders",
    "abs_holder": "tool_holders",
    "masbt_holder": "tool_holders",
    "bmt_holder": "tool_holders",
    "mk_holder": "tool_holders",
    "varilock_holder": "tool_holders",
    "varia_holder": "tool_holders",
    "km_holder": "tool_holders",
    # grinding
    "grinding_wheel": "grinding_tools",
    "grinding_pin": "grinding_tools",
    "honing_stone": "grinding_tools",
    "dressing_tool": "grinding_tools",
    "cutting_disc": "grinding_tools",
    "flap_wheel": "grinding_tools",
    "abrasive_belt": "grinding_tools",
    "abrasive_disc": "grinding_tools",
    # other tool families
    "brush": "brushes",
    "broach": "broaches",
    "honing_reamer": "honing_tools",
    "gear_cutter": "gear_cutting",
    "center_point": "center_points",
    "welding_consumable": "welding",
    "punch_die": "punching",
    "form_steel": "form_steel",
    # screws & generic accessories
    "screw": "screws",
    "wrench": "accessories",
    "accessory": "accessories",
    # PPE and other
    "ppe": "ppe",
    "other": "other",
}

SCREW_KEYWORDS = [
    "screw",
    "schraube",
    "schrauben",
    "vis",
    "vite",
    "viti",
    "tornillo",
    "tornillos",
    "parafuso",
    "parafusos",
    "torx",
]

ACCESSORY_KEYWORDS = [
    "access",
    "accessory",
    "accessories",
    "zubehör",
    "zubehoer",
    "ersatz",
    "spare",
    "clamp",
    "klemm",
    # Kromi Zubehör L2 names
    "kassette",  # Cassette / cartridge holder
    "kühlmittelrohr",  # Coolant pipe
    "kuehlmittelrohr",
    "schlüssel",  # Wrench/key (NOT "key" — too generic)
    "schluessel",
    "skalenkonus",  # Scale cone
    "spannelement",  # Clamping element
    "spannmittel",  # Clamping device
    "spannzange",  # Collet
    "spannhülse",  # Collet sleeve
    "spannhuelse",
    "unterlegplatte",  # Shim plate
    "unterlegscheibe",  # Washer / shim
    "passfeder",  # Feather key
    "rohrstift",  # Pin
    "kniehebel",  # Toggle lever
    "verstellelement",  # Adjustment element
    "messtastereinsatz",  # Measuring probe insert
    "gewindebuchse",  # Threaded bush
    "gewindestift",  # Threaded pin / grub screw
]

# Personal Protective Equipment — multilingual, intentionally broad.
PPE_KEYWORDS = [
    # Gloves
    "glove",
    "gloves",
    "gant",
    "gants",
    "handschuh",
    "handschuhe",
    "guante",
    "guantes",
    "luva",
    "luvas",
    # Eye protection
    "goggle",
    "goggles",
    "safety glass",
    "safety glasses",
    "lunette",
    "lunettes",
    "brille",
    "schutzbrille",
    "gafa",
    "gafas",
    "óculos",
    # Hearing protection
    "earplug",
    "ear plug",
    "earmuff",
    "hearing protection",
    "bouchon",
    "bouchon d'oreille",
    "ohrstöpsel",
    "ohrstopsel",
    "tapone",
    "tapones",
    # Respiratory
    "mask",
    "masque",
    "maske",
    "mascarilla",
    "máscara",
    "respirator",
    "respirateur",
    "atemschutz",
    "filter",
    "filtre",
    "filtro",
    "filtr",
    # Body protection
    "coverall",
    "overall",
    "combinaison",
    "traje de proteccion",
    "schutzanzug",
    "apron",
    "tablier",
    "schürze",
    "delantal",
    # Foot protection
    "safety boot",
    "safety shoe",
    "steel toe",
    "chaussure de securite",
    "chaussure de sécurité",
    "sicherheitsschuh",
    "bota de seguridad",
    "zapato de seguridad",
    # Head protection
    "helmet",
    "hard hat",
    "casque",
    "helm",
    "casco",
    "capacete",
    # PPE abbreviations
    "ppe",
    "epi",
    "psa",
    "schutzausruestung",
    "schutzausrüstung",
]

INSERT_KEYWORDS = [
    "insert",
    "insert for",
    "wendeschneidplatte",
    "wendeplatte",
    "wsp",
    "führungsleiste",  # Guide bar — Kromi L2 under Wendeschneidplatten
    "fuehrungsleiste",
    "plaquette",
    "wnmg",
    "cnmg",
    "cnmm",
    "cnma",
    "cnga",
    "dnmg",
    "dnmm",
    "dnma",
    "dnga",
    "snmg",
    "tnmg",
    "vnmg",
    "ccmt",
    "dcgt",
    "vcgt",
    "vbmt",
    "rcmt",
    "spgt",
    "tcmt",
    "tpkn",
    "apkt",
    "adkt",
    "lnmt",
    "lnht",
    "tckt",
    "ancx",
    "wxcu",
    "qpmt",
]

DRILL_KEYWORDS = [
    # Order matters: specific compounds FIRST so derive_tool_class can lift L2 detail.
    "bohrfräser",  # Hole cutter — Kromi: under Bohrer L1
    "bohrfraeser",
    "bohrreibahle",  # Drill reamer — Kromi: under Bohrer L1
    "bohrsenker",  # Drill countersink — Kromi: under Bohrer L1
    "bohrkrone",  # Core drill / hole saw
    "wechselkopf bohren",
    "wechselkopf-bohren",
    "spiralbohrer",
    "vhm-bohrer",
    # Generic — only matches when no specific compound did
    "drill",
    "bohrer",
    "foret",
    # Other multilingual variants
    "wiertło",  # Polish
    "vrták",  # Czech / Slovak
    "broca",  # Portuguese / Spanish
    "sveder",  # Slovenian
    "bor",  # Danish
]

MILL_KEYWORDS = [
    # Specific compounds first
    "frässtift",
    "fraesstift",
    "kreissägeblatt",
    "kreissaegeblatt",
    "wälzfräser",
    "waelzfraeser",
    "wechselkopf fräsen",
    "wechselkopf-fräsen",
    "wechselkopf fraesen",
    "vhm-fräser",
    "vhm-fraeser",
    "endmill",
    # Generic
    "mill",
    "fräser",
    "fraeser",
    "fraise",
    "milling",
    # Multilingual
    "frez",
    "fréza",
    "fresa",
    "rezkar",
]

REAMER_KEYWORDS = [
    "reamer",
    "reibahle",
    "alesoir",
    "alésoir",  # French spelling with accent
    "rozwiertak",  # Polish
    "výhrubník",  # Czech
    "alargador",  # Portuguese
    "escariador",  # Portuguese / Spanish
]

# ----- Kromi-aligned keyword lists -----
# Multilingual, derived from kromi-structure-translations-v3.xlsx L2 names.
# Curated for precision: short generic words ("die", "tap") word-boundary only;
# compound German words use full form to avoid substring collisions.

# Taps — Kromi L2: Gewindebohrer / Gewindeformer (cold-form taps).
# CRITICAL: "gewindebohrer" must be checked BEFORE "bohrer" to prevent the
# tap-as-drill misclassification bug.
TAP_KEYWORDS = [
    # German
    "gewindebohrer",
    "gewindeformer",
    # English
    "tap",
    "thread tap",
    "thread molder",
    "thread former",
    # French
    "taraud",
    "mouleur de filets",
    # Spanish / Portuguese
    "macho",
    "macho de roscar",
    "macho de laminacion",
    # Polish / Czech / Slovak
    "gwintownik",
    "závitník",
    "závitník tvářecí",
    "tvarovací závitník",
    # Danish
    "gevindtap",
    "gevindformer",
    # Slovenian
    "sveder navojni",
    "vtiskovalec",
]

# Thread mills — Kromi L2: Gewindefräser / Gewindebohrfräser
THREAD_MILL_KEYWORDS = [
    # German
    "gewindefräser",
    "gewindefraeser",
    "gewindebohrfräser",
    "gewindebohrfraeser",
    # English
    "thread mill",
    "thread cutter",
    "thread hole cutter",
    "threading mill",
    # French
    "fraise à fileter",
    "fraise a fileter",
    "taraudeuse",
    # Spanish / Portuguese
    "fresa de roscar",
    "fresa de roscado",
    "fresa de taladrado y roscado",
    "fresa para roscar",
    # Polish / Czech
    "frez do gwintu",
    "frez do gwintowania",
    "závitová fréza",
    "závitníková fréza",
    "závitová vrtací fréza",
    # Danish
    "gevindfræser",
    "tapfræser",
]

# Thread dies — Kromi L2: Schneideisen / Gewinderoller
THREAD_DIE_KEYWORDS = [
    # German
    "schneideisen",
    "gewinderoller",
    # English
    "threading die",
    "thread rolling die",
    "thread die",
    # French
    "filière",
    # Spanish / Portuguese
    "terraja",
    "cossinete",
    "rodillo de roscar",
    # Polish / Czech / Slovak
    "narzynka",
    "závitové čelisti",
    "závitové želiezko",
    # Danish
    "skærebakke",
]

# Counterbores — Kromi L1: Senker
COUNTERBORE_KEYWORDS = [
    # German — full compound forms only; the bare "senken" was removed
    # because it matches "WSP Senken" (countersinking insert, → inserts) and
    # "zum Senken" (holder for countersinking, → holders).
    # "bohrsenker" was REMOVED — Kromi taxonomy classifies it under Bohrer L1
    # (drill countersink), not Senker L1.
    "kegelsenker",
    "flachsenker",
    "rückwärtssenker",
    "rueckwaertssenker",
    "stufensenker",
    "entgratgabel",
    # English
    "countersink",
    "counterbore",
    "back countersink",
    "step countersink",
    "flat countersink",
    "deburring fork",
    # French
    "fraise conique",
    "fraise inversée",
    "fraise inversee",
    "foret-aléseur en bout",
    "foret-aleseur en bout",
    "foret-aléseur étagé",
    "foret-aleseur etage",
    "outil à ébavurer à fourche",
    "outil a ebavurer a fourche",
    # Spanish / Portuguese
    "avellanador",
    "avellanador inverso",
    "avellanador plano",
    "avellanador escalonado",
    "desbarbador",
    "escareador cônico",
    "escareador conico",
    "escareador escalonado",
    "escareador reverso",
    # Polish / Czech / Slovak
    "pogłębiacz",
    "pogłębiacz stopniowy",
    "pogłębiacz stożkowy",
    "pogłębiacz wsteczny",
    "gratownik",
    "kužeľový záhlbník",
    "odhrotovacia vidlica",
    "odhrotovací nástroj",
    # Danish
    "bagsænker",
    "afgratningsværktøj",
    "flertrinsskær",
]

# Tool holders (machine-spindle interfaces) — Kromi L1: Werkzeugaufnahme
# These are mostly fixed engineering codes (HSK/SK/VDI/Capto/etc.) — same across
# all languages. Most are <= 6 chars so word-boundary matching applies.
# Order matters: longer/more-specific codes first so e.g. "MASBT40" matches
# before any partial pattern.
#
# Words intentionally OMITTED to avoid substring false-positives:
#   "varia"   — matches "VARIANT" / "variation" in descriptions
#   "morse"   — matches "morse code" in technical text (unlikely but possible)
#   "capto"   — matches as 5-char substring; safe in practice but
#               we keep specific "capto" anyway since real-world description
#               substrings containing "capto" are rare
TOOL_HOLDER_KEYWORDS = [
    # HSK family
    "hsk32",
    "hsk50",
    "hsk63",
    "hsk100",
    "hsk",
    # SK / MAS-BT family
    "masbt32",
    "masbt40",
    "masbt50",
    "sk30",
    "sk40",
    "sk45",
    "sk50",
    # VDI family
    "vdi16",
    "vdi20",
    "vdi25",
    "vdi30",
    "vdi40",
    "vdi50",
    "vdi",
    # ABS family
    "abs25",
    "abs32",
    "abs40",
    "abs50",
    "abs63",
    "abs80",
    "abs100",
    # Other quick-change interfaces — but only specific codes, no generic brand names
    "capto",
    "varilock",
    "bmt45",
    # 2-letter spindle interfaces (KM = Kennametal, MK = Morse Kegel = Morse Taper)
    # 2 chars ≤ 4 → word boundary matching, safe.
    "km",
    "mk",
    # Cone Morse
    "cône morse",
    "cone morse",
    # Generic German names — compound words, safe
    "spannzangenfutter",
    "werkzeugaufnahme",
    "werkzeughalter",
    "schrumpffutter",
    "hydrodehnspannfutter",
    "kraftspannfutter",
    # Generic English / French
    "shrink fit holder",
    "shrink fit chuck",
    "porte-outil de broche",
]

# Grinding tools — Kromi L1: Schleifkörper
GRINDING_TOOL_KEYWORDS = [
    # German
    "schleifscheibe",
    "schleifstift",
    "schleifstein",
    "schleifband",
    "schleifkappen",
    "schleiffächer",
    "schleiffaecher",
    "abrichter",
    "abrichtkugel",
    "trennscheibe",
    "honstein",
    "honhülse",
    "honhuelse",
    "flex-hone",
    "flex hone",
    # English
    "grinding wheel",
    "grinding pin",
    "grinding stone",
    "grindstone",
    "dressing tool",
    "dressing wheel",
    "cutting disc",
    "cutting disk",
    "flap wheel",
    "honing stone",
    "honing sleeve",
    # French
    "meule",
    "disque à meuler",
    "disque a meuler",
    "bande abrasive",
    "molette à dresser",
    "molette a dresser",
    # Spanish / Portuguese
    "muela",
    "disco abrasivo",
    "rebolo",
    "pedra de afiar",
    "dressador",
    "molete diamantado",
    # Polish / Czech / Slovak
    "ściernica",
    "kotouč brusný",
    "brusný kotouč",
    "brusný kámen",
    "brusná čepička",
    "brusný pás",
    "brusné tělísko",
    "dělící kotouč",
    "lamelový brusný kotouč",
    "honovací kámen",
    "honovací pouzdro",
    # Danish
    "slibeskive",
    "slibestift",
    "slibesten",
    "slibebånd",
    "afretter",
    "afretterkugle",
    "afskaereskive",
]

# Brushes — Kromi L1: Bürste. Single L1 only.
BRUSH_KEYWORDS = [
    "bürste",
    "buerste",
    "brush",
    "wire brush",
    "brosse",
    "cepillo",
    "escova",
    "szczotka",
    "kartáč",
    "kefa",
    "ščetka",
    "børste",
]

# Broaches — Kromi L1: Räumwerkzeug. Single L1.
BROACH_KEYWORDS = [
    "räumwerkzeug",
    "raeumwerkzeug",
    "räumnadel",
    "raeumnadel",
    "broach",
    "broaching tool",
    "brocheur",
    "broche d'usinage",
    "brochador",
    "brocha",
    "brochadora",
    "narzędzie do przeciągania",
    "protahovací nástroj",
    "obtahovák",
    "rømmeværktøj",
]

# Honing tools — Kromi L1: Honahlen
HONING_TOOL_KEYWORDS = [
    "honahle",
    "honwerkzeug",
    "honleiste",
    "honing reamer",
    "honing tool",
    "alesoir de rodage",
    "alargador para brunir",
    "honovací výstružník",
    "honovací nástroj",
]

# Gear cutting — Kromi L1: Verzahnungswerkzeug.
# Note: "Wälzfräser" is a milling cutter in Kromi taxonomy (under Fräser L1),
# not gear-cutting — so we don't include it here. Real gear-cutting is
# Stoßwerkzeug (gear shaping cutter).
GEAR_CUTTING_KEYWORDS = [
    "verzahnungswerkzeug",
    "stoßwerkzeug",
    "stosswerkzeug",
    "gear cutter",
    "broaching tool id",
    "broaching tool od",
    "fraise de taillage",
    "outil de taillage",
    "mortajado interior",
    "mortajado exterior",
    "cabeçote especial",
    "narzędzie do nacinania zębów",
    "ozubovací nástroj",
]

# Center points — Kromi L1: Zentrierspitzen
CENTER_POINT_KEYWORDS = [
    "zentrierspitze",
    "mitlaufende zentrierspitze",
    "stirnseitenmitnehmer",
    "stirnseiten mitnehmer",
    "live center",
    "solid center",
    "face driver",
    "punto",
    "contrapunto",
    "contra punto",
    "contra-punto",
    "punto giratorio",
    "punta giratoria",
    "ponta giratória",
    "ponta fixa",
    "kieł obrotowy",
    "kieł stały",
    "středicí hrot",
]

# Welding consumables — Kromi L1: Schweißen. Single L1.
WELDING_KEYWORDS = [
    "schweißen",
    "schweissen",
    "schweißelektrode",
    "schweisselektrode",
    "schweißdraht",
    "schweissdraht",
    "schweisszusatz",
    "welding electrode",
    "welding wire",
    "welding filler",
    "tig electrode",
    "mig wire",
    "filler rod",
    "électrode de soudage",
    "fil de soudage",
    "electrodo de soldadura",
    "alambre de soldadura",
    "elektroda spawalnicza",
    "drut spawalniczy",
    "svařovací elektroda",
    "svařovací drát",
]

# Punching tools — Kromi L1: Stanzwerkzeug
PUNCHING_KEYWORDS = [
    "stanzwerkzeug",
    "stanzstempel",
    "stanzmatrize",
    "punch",
    "punching tool",
    "punch die",
    "matrize",
    "poinçon",
    "poinçonnage",
    "matrice de poinçonnage",
    "punzón",
    "matriz de punzonado",
    "punção",
    "matriz de punção",
    "stempel wykrojnika",
    "děrovací nástroj",
    "razník",
]

# Form steel — Kromi L1: Formstahl. Tool-steel blanks shaped for turning.
FORM_STEEL_KEYWORDS = [
    "formstahl",
    "formdrehstahl",
    "abstechstahl",
    "form tool",
    "form turning tool",
    "shaped lathe tool",
    "outil à former",
    "outil de tournage à former",
    "herramienta de forma",
    "ferramenta de forma",
    "tvarový nůž",
    "tvarový soustružnický nůž",
]


HOLDER_KEYWORDS = [
    "holder",
    "halter",
    "aufnahme",
    "toolholder",
    "spannfutter",
    # Kromi Halter L2 names. These are "for X" turning/milling/drilling
    # holders that hold inserts. They go in PC=holders (insert holders), distinct
    # from PC=tool_holders (machine-spindle interfaces).
    "klemmhalter",  # Clamp holder
    "glockenwerkzeug",  # Bell tool
    "feinbohrwerkzeug",  # Fine boring tool
    "kurzklemmhalter",  # Cartridge
    "drehmeißel",  # Turning tool
    "drehmeissel",
    # The "zum X" L2 names from Halter are intentionally NOT added — they're too
    # ambiguous ("zum Bohren" matches anything mentioning boring). The compound
    # forms above and supplier-pattern matching handle most real-world cases.
]

# French SAP catalogs commonly use 2-letter shorthand at the start of
# descriptions. AI struggles with these unless the rest of the text carries
# enough context. Matched against the raw uppercase description with word
# boundaries — never inside other words.
DRILL_SHORTHAND_FR = ["FO"]  # Foret

MILL_SHORTHAND_FR = ["FR"]  # Fraise

REAMER_SHORTHAND_FR = ["AL"]  # Alésoir

GRINDING_SHORTHAND_FR = ["ME"]  # Meule

SUPPLIER_CODE_PATTERNS = [
    # (supplier_brand_substring, regex_anchored, category, tool_class, evidence_tag)
    # Seco — proprietary grade codes and indexable insert families
    ("seco", r"^TP\d{3,5}[A-Z]?$", "inserts", "turning_insert", "seco:TP_grade"),
    ("seco", r"^TS\d{3,5}[A-Z]?$", "inserts", "turning_insert", "seco:TS_grade"),
    ("seco", r"^CP\d{3,5}[A-Z]?$", "inserts", "turning_insert", "seco:CP_grade"),
    ("seco", r"^MK\d{3,5}[A-Z]?$", "inserts", "turning_insert", "seco:MK_grade"),
    ("seco", r"^MM\d{3,5}[A-Z]?$", "inserts", "milling_insert", "seco:MM_grade"),  # MM = milling
    ("seco", r"^MS\d{3,5}[A-Z]?$", "inserts", "turning_insert", "seco:MS_grade"),
    ("seco", r"^WS\d{3,4}$", "inserts", "turning_insert", "seco:WS_grade"),
    ("seco", r"^WNW\d{2,3}[A-Z]+$", "inserts", "turning_insert", "seco:WNW_family"),
    ("seco", r"^PP\d{4}(-\d+)?$", "inserts", "turning_insert", "seco:PP_family"),  # parting
    ("seco", r"^WA[EI]\d{6}$", "inserts", "milling_insert", "seco:WAE_WAI_family"),
    ("seco", r"^SD\d{3,4}[-\d.]*-P?$", "drills", "solid_carbide_drill", "seco:SD_solid_drill"),
    # Iscar — IC grade codes (very common)
    ("iscar", r"^IC\d{3,4}[A-Z]?$", "inserts", "turning_insert", "iscar:IC_grade"),
    ("iscar", r"-IC\d{3,4}[A-Z]?$", "inserts", "turning_insert", "iscar:IC_grade_suffix"),
    # Sandvik — long numeric codes (5xxx family is mostly inserts)
    ("sandvik", r"^53\d{2}-\d{3}-\d{2,3}$", "inserts", "turning_insert", "sandvik:5300_family"),
    ("sandvik", r"^54\d{2}-\d{3}-\d{2,3}$", "inserts", "turning_insert", "sandvik:5400_family"),
    ("sandvik", r"^170\.\d-\d{3}$", "inserts", "turning_insert", "sandvik:170_family"),
    # Mitsubishi — grade codes (VP15TF, MP9015, UTI20T, UE6020 etc.)
    # Note: codes are uppercased before matching, so 'UTi' becomes 'UTI'.
    (
        "mitsubishi",
        r"^(UTI|VP|MP|UE|US|MS)\d{2,4}[A-Z]{0,3}$",
        "inserts",
        "turning_insert",
        "mitsubishi:grade",
    ),
    (
        "mitsubishi",
        r"-(UTI|VP|MP|UE|US|MS)\d{2,4}[A-Z]{0,3}$",
        "inserts",
        "turning_insert",
        "mitsubishi:grade_suffix",
    ),
    # Kennametal — KC grade codes
    ("kennametal", r"^KC\d{3,4}[A-Z]?$", "inserts", "turning_insert", "kennametal:KC_grade"),
    ("kennametal", r"^K\d{3,4}[A-Z]?$", "inserts", "turning_insert", "kennametal:K_grade"),
]

# Suppliers whose catalog is strongly dominated by one product type.
# Soft fallback: only fires when no other classification succeeded.
# Format: { supplier_substring (lowercase): (category, tool_class, evidence_tag) }
SUPPLIER_SPECIALTY = {
    "guhring": ("drills", "solid_carbide_drill", "guhring_specialty"),
    "tivoly": ("drills", "solid_carbide_drill", "tivoly_specialty"),
    "ffdm tivoly": ("drills", "solid_carbide_drill", "tivoly_specialty"),
    "botek": ("drills", "solid_carbide_drill", "botek_specialty"),
    "mapal": ("reamers", "reamer", "mapal_specialty"),
    "asahi diamond": ("accessories", "grinding_wheel", "asahi_diamond_specialty"),
}

BORING_BAR_KEYWORDS = [
    "bohrstange",
    "boring bar",
    "boringbar",
]

# Pack-size text extraction patterns (opt-in via sidebar)
PACK_HINT_PATTERNS: list[tuple[str, str]] = [
    (r"\bqte\s*[:=]?\s*(\d{1,4})\b", "qte"),
    (r"\bqté\s*[:=]?\s*(\d{1,4})\b", "qte"),
    (r"\bqty\s*[:=]?\s*(\d{1,4})\b", "qty"),
    (r"\blot\s+de\s+(\d{1,4})\b", "lot"),
    (r"\blot\s+par\s+(\d{1,4})\b", "lot"),
    (r"\bbo[iî]te\s+de\s+(\d{1,4})\b", "boite"),
    (r"\bbox\s+of\s+(\d{1,4})\b", "box"),
    (r"\bcarton(?:\s+de)?\s+(\d{1,4})\b", "carton"),
    (r"\bpack(?:\s+of)?\s+(\d{1,4})\b", "pack"),
    (r"\bsachet\s+de\s+(\d{1,4})\b", "sachet"),
    (r"\bpar\s+(\d{1,4})\s*(?:pcs?|pieces?|pi[eè]ces?)\b", "par-pcs"),
    (r"\bpaquet\s+de\s+(\d{1,4})\b", "paquet"),
    (r"\bbag\s+of\s+(\d{1,4})\b", "bag"),
]

# Item-family detection for optional bulk routing
BULK_ALWAYS_FAMILIES = {
    "abrasive_discs",
    "paint_consumables",
    "tapes_labels",
    "cloth_wipes",
    "adhesives_sealants",
}

DISPOSABLE_PPE_FAMILIES = {"disposable_ppe", "respirator_filters"}

# Default tool_class fallback when only product_category is known.
# Coarser than TOOLCLASS_TO_PRODUCT_CATEGORY (which goes the other way).
TOOLCLASS_FROM_PRODUCT_CATEGORY = {
    "inserts": "turning_insert",  # turning is the dominant family
    "drills": "solid_carbide_drill",
    "mills": "solid_end_mill",
    "reamers": "reamer",
    "holders": "milling_holder",
    "screws": "screw",
    "accessories": "accessory",
    "boring_bars": "boring_bar",
    "ppe": "ppe",
    "other": "other",
    # Kromi-aligned additions
    "taps": "tap",
    "thread_mills": "thread_mill",
    "thread_dies": "threading_die",
    "counterbores": "countersink",
    "tool_holders": "hsk_holder",  # HSK is the most common interface
    "grinding_tools": "grinding_wheel",
    "brushes": "brush",
    "broaches": "broach",
    "honing_tools": "honing_reamer",
    "gear_cutting": "gear_cutter",
    "center_points": "center_point",
    "welding": "welding_consumable",
    "punching": "punch_die",
    "form_steel": "form_steel",
}

# Keyword → specific ToolClass map for L2 detail lift.
# When the classifier returns `evidence = "keyword:gewindeformer"`, we can be
# MORE specific than the PC default ("tap") — gewindeformer is a thread former
# (cold-forming tap, no chips). This map is consulted in derive_tool_class
# before falling back to TOOLCLASS_FROM_PRODUCT_CATEGORY[pc].
KEYWORD_TO_TOOLCLASS = {
    # Taps
    "gewindeformer": "tap_carbide",  # rough proxy — most thread formers are carbide
    "gevindformer": "tap_carbide",
    "thread former": "tap_carbide",
    "thread molder": "tap_carbide",
    "mouleur de filets": "tap_carbide",
    # Mills (Kromi Fräser L2 lift)
    "frässtift": "burr",
    "fraesstift": "burr",
    "kreissägeblatt": "saw_blade",
    "kreissaegeblatt": "saw_blade",
    "wälzfräser": "form_mill",  # Hob — closest in our taxonomy
    "waelzfraeser": "form_mill",
    # Drills (Kromi Bohrer L2 lift)
    "bohrsenker": "center_drill",  # Drill countersink
    "bohrreibahle": "core_drill",  # Drill reamer — closest match
    "bohrfräser": "core_drill",  # Hole cutter (drill/mill hybrid)
    "bohrfraeser": "core_drill",
    # Tool holders (Kromi Werkzeugaufnahme L2 lift)
    "hsk32": "hsk_holder",
    "hsk50": "hsk_holder",
    "hsk63": "hsk_holder",
    "hsk100": "hsk_holder",
    "hsk": "hsk_holder",
    "sk30": "sk_holder",
    "sk40": "sk_holder",
    "sk45": "sk_holder",
    "sk50": "sk_holder",
    "masbt32": "masbt_holder",
    "masbt40": "masbt_holder",
    "masbt50": "masbt_holder",
    "vdi16": "vdi_holder",
    "vdi20": "vdi_holder",
    "vdi25": "vdi_holder",
    "vdi30": "vdi_holder",
    "vdi40": "vdi_holder",
    "vdi50": "vdi_holder",
    "vdi": "vdi_holder",
    "abs25": "abs_holder",
    "abs32": "abs_holder",
    "abs40": "abs_holder",
    "abs50": "abs_holder",
    "abs63": "abs_holder",
    "abs80": "abs_holder",
    "abs100": "abs_holder",
    "capto": "capto_holder",
    "varilock": "varilock_holder",
    "bmt45": "bmt_holder",
    "km": "km_holder",
    "mk": "mk_holder",
    # Grinding tools (Kromi Schleifkörper L2 lift)
    "schleifscheibe": "grinding_wheel",
    "schleifstift": "grinding_pin",
    "schleifstein": "honing_stone",  # close enough
    "schleifband": "abrasive_belt",
    "honstein": "honing_stone",
    "honhülse": "honing_stone",
    "honhuelse": "honing_stone",
    "abrichter": "dressing_tool",
    "abrichtkugel": "dressing_tool",
    "trennscheibe": "cutting_disc",
    "schleiffächer": "flap_wheel",
    "schleiffaecher": "flap_wheel",
    "flex-hone": "honing_stone",
    # Counterbores (Senker L2 lift)
    "kegelsenker": "countersink",
    "flachsenker": "flat_countersink",
    "rückwärtssenker": "back_countersink",
    "rueckwaertssenker": "back_countersink",
    "stufensenker": "step_countersink",
    "entgratgabel": "deburring_fork",
    # Inserts (Wendeschneidplatten L2 lift via WSP-prefix in description)
    # The L2 (WSP Drehen/Fräsen/Bohren) is already lifted via ISO prefix logic
    # in derive_tool_class. Here we handle the WSP-keyword path: it returns
    # the PC default "turning_insert" which is fine.
}

# slide-style 4-bucket mapping for distribution pies
SLIDE_DISTRIBUTION_BUCKETS = {
    "inserts": "Inserts",
    "mills": "Mills",
    "drills": "Drills",
    # Everything else folds into "Others" via the getter below.
}

SLIDE_BUCKET_ORDER = ["Inserts", "Mills", "Drills", "Others"]

# Map ToolClass values to the 4 primary buckets used in the slide-style view.
# Order inside each list controls the display order in the subclass breakdown.
TOOLCLASS_TO_BUCKET = {
    # Inserts
    "turning_insert": "Inserts",
    "milling_insert": "Inserts",
    "drilling_insert": "Inserts",
    "grooving_insert": "Inserts",
    "threading_insert": "Inserts",
    "reaming_insert": "Inserts",
    # Mills
    "solid_end_mill": "Mills",
    "shell_mill": "Mills",
    "face_mill": "Mills",
    "thread_mill": "Mills",
    "disc_mill": "Mills",
    "burr": "Mills",
    "saw_blade": "Mills",
    "form_mill": "Mills",
    "ball_track_mill": "Mills",
    "radius_mill": "Mills",
    "t_slot_mill": "Mills",
    "thread_former": "Mills",
    "thread_hole_cutter": "Mills",
    # Drills
    "solid_carbide_drill": "Drills",
    "indexable_drill": "Drills",
    "hss_drill": "Drills",
    "spiral_drill": "Drills",
    "step_drill": "Drills",
    "nc_drill": "Drills",
    "center_drill": "Drills",
    "deep_hole_drill": "Drills",
    "core_drill": "Drills",
    "pilot_drill": "Drills",
    # Others — every other tool class
    "tap": "Others",  # taps are now in Others (was Drills)
    "tap_carbide": "Others",
    "tap_hss": "Others",
    "threading_die": "Others",
    "thread_roller": "Others",
    "reamer": "Others",
    "multi_stage_reamer": "Others",
    "countersink": "Others",
    "flat_countersink": "Others",
    "back_countersink": "Others",
    "step_countersink": "Others",
    "deburring_fork": "Others",
    "boring_bar": "Others",
    "turning_holder": "Others",
    "milling_holder": "Others",
    "drilling_holder": "Others",
    "boring_holder": "Others",
    "reaming_holder": "Others",
    "grooving_holder": "Others",
    "collet": "Others",
    "hsk_holder": "Others",
    "sk_holder": "Others",
    "vdi_holder": "Others",
    "capto_holder": "Others",
    "abs_holder": "Others",
    "masbt_holder": "Others",
    "bmt_holder": "Others",
    "mk_holder": "Others",
    "varilock_holder": "Others",
    "varia_holder": "Others",
    "km_holder": "Others",
    "grinding_wheel": "Others",
    "grinding_pin": "Others",
    "honing_stone": "Others",
    "dressing_tool": "Others",
    "cutting_disc": "Others",
    "flap_wheel": "Others",
    "abrasive_belt": "Others",
    "abrasive_disc": "Others",
    "brush": "Others",
    "broach": "Others",
    "honing_reamer": "Others",
    "gear_cutter": "Others",
    "center_point": "Others",
    "welding_consumable": "Others",
    "punch_die": "Others",
    "form_steel": "Others",
    "screw": "Others",
    "wrench": "Others",
    "accessory": "Others",
    "ppe": "Others",
    "other": "Others",
}
