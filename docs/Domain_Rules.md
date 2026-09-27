# Domain rules

The planning arithmetic the owner has validated. Most rules are pinned by tests;
change one only after arguing the case with the owner (CLAUDE.md, rule 1).

## Units

- **VPE** (Verpackungseinheit) is the packaging unit: pieces per pack. Demand is
  counted in pieces for routing and in packs for physical sizing.
- **Monthly_pcs** decides KTC versus Kanban (per-row threshold); **Monthly_packs**
  decides Helix versus Carousel and sizes the space.
- Consumption is recorded identically on the customer-property number and on its
  KROMI counterpart. Never add the two.
- VPE corrections reshuffle the ranking a lot (about a third of the articles in
  one validated onboarding). Check VPE before trusting a plan.

## Cabinet types and capacity

| Type | Unit | Capacity per cabinet |
|---|---|---|
| Helix | spirals | 70 |
| Carousel | compartments | 720 |
| Locker A / B / C | boxes | 48 / 72 / 96 |

- Size XXL goes to Locker A, XXLS to Locker B, XLS to Locker C. Otherwise Helix when
  Monthly_packs exceeds the Helix threshold, else Carousel.
- Packs per spiral by size: S 28, M 22, L 18, XL 12; by category when the size is
  unknown (inserts 28, drills 22, else 18). The physical machine holds 22 packs
  per spiral; the S = 28 value is a known calibration gap still open.
- Helix spirals: 1 when demand fits one spiral times the overfill factor (default
  1.10), else ceil(demand / capacity). A regrind article gets at least 2 spirals.
- Carousel compartments: max(minimum allocation, ceil(Target_packs x reserve 0.85)),
  with Target_packs = Monthly_packs x coverage days / 30.4375.
- The Helix threshold must match the catalog's pack-rate scale. On a real
  10-pack insert catalog about 1.45 packs/month separated Helix from Carousel
  correctly; the old default of 6 to 7 inverted the routing.

## Articles on several machines (v34.63)

- The Program column is mapped per machine. A location cell may name several
  machines, separated by `+`, `&`, `;` or `,` (`/` and `-` are part of a name).
  Labels are read in one spelling: `AB 101`, `ab-101` and `AB101` are `AB-101`;
  a bare number takes the letter prefix of the nearest earlier machine
  (`AB-100 +101` names `AB-100` and `AB-101`).
- Every machine is mapped to a supply point or to "Not planned here". A
  dropdown starts empty; the run waits until every machine has a choice.
- D1 Consumption: an article listed for k machines gives each machine an
  equal share (1/k); a supply point receives the shares of the listed machines
  mapped to it (two of three machines on one supply point give 2/3). A machine
  that is not planned keeps its share out of the plan. Option, off by
  default: "Count the full consumption in every supply point".
- D4: an article whose machines are all "Not planned here" stops the run with
  its code; map a machine (an extra supply point with no machines is fine) or
  remove the rows. An article is never dropped silently.
- An article is never KTC and Kanban at once (owner decision 2026-09-27): when
  one supply point's share makes it KTC, it is KTC in every supply point, each
  copy sized from its own share.
- A file without multi-machine cells plans exactly as before.

## Fixed configuration (existing machines)

- The machines per supply point are given; usable space = physical x (100 -
  headroom) % (headroom 0 to 90). The headroom stays empty.
- Articles are placed most used first (Monthly_pcs, then Monthly_packs, then
  code). Overflow may move S/M Carousel articles to the Helix and Helix articles to
  the Carousel (switchable), lockers C to B to A. A technician's cabinet-type
  override never moves.
- Articles without space are marked "Not placed" and listed; they are never
  dropped.
- Stock-based Helix promotion (switchable, off by default): where consumption is
  missing, the customer's stock is assumed to cover N months (default 3). After
  the fit, free Helix space takes S/M Carousel articles whose stock / VPE / N
  exceeds the Helix threshold and the recorded use, highest first, only when all
  their spirals fit. It changes the cabinet type and the takeover maximum,
  nothing else.
- Are the configured machines enough (v34.63)? Per supply point and machine
  type, "Needed by not placed" is the space (spirals, compartments or boxes)
  the not-placed articles need in their own machine type, with the fit's
  footprint; "Extra machines (estimate)" = ceil(max(0, needed - free) /
  usable units per machine), usable after the headroom. A type without
  machines is listed when it is needed. The page says it in one line per
  supply point.

## Takeover sheets

- Every takeover is customer property. One sheet per supply point.
- Whole packs go into the KTC up to the maximum; the rest stays at the main stock
  location (HLO).
- Maximum: Carousel = compartments x VPE; Helix = spirals x packs per spiral x
  VPE (a regrind article keeps one spiral free). Lockers, Kanban and not-placed
  articles hold nothing in the KTC.
- Replicate mode shares one stock pool across supply points, filled in supply
  point order; with a Program mapping each supply point uses its own stock.
- D5 (v34.63), when a cell names several machines: one stock pool per article
  (Listing, Code), its stock in the list with each source row that reaches the
  plan counted once (a row whose machines are all "Not planned here" adds
  none). The pool fills the article's supply points in supply-point order with
  whole packs up to each maximum; the rest stays at the HLO on the first
  supply point's line, the other lines show 0 at the HLO, and a "Hinweis"
  column names the other supply points ("Bestand geteilt mit SP 2"). Stock is
  never counted twice across the sheets.
- In machine data, the maximum stock counts pieces: Helix = 22 x VPE per spiral,
  Carousel = compartments x VPE.

## Article numbers

- 12 digits. KTC articles use a counter scheme, Kanban articles a dimension
  scheme (the dimension digits come from the mapped Description, so map the
  dimension-rich column there).
- Numbers are a per-run result. They are not stored between runs (owner decision
  2026-09-22): number a customer's complete list in one run with one KTC-ID.
- The Article setup sheet lists KTC articles twice (customer-property predecessor,
  KROMI-property successor) and Kanban articles once (customer property).
- A provided structure word for step drills gives code 14; threading inserts stay
  code 12.
- D6 (v34.63): an article planned in several supply points because a cell
  names several machines has one number. The KTC counter and the
  dimension-scheme variants advance once per article, and every copy shows the
  article's number. A file split over several supply points gets exactly the
  Article setup and numbers of the same file with each article in one supply
  point. Replicate copies keep one number per row (with the documented gaps),
  and so does an article repeated on single-machine rows in a file without
  multi-machine cells.
- One numbering per workbook (v34.64): the plan is numbered once, and every
  sheet shows the Result sheet's number: KTC_only, Kanban_only, Helix_only,
  Carousel_only, Not_placed and Bulk_Routed for the same row, the takeover
  sheets and the Article setup predecessors for the article's first row. When
  the plan cannot be numbered, no sheet shows a number. Workbooks exported
  before v34.64 can show wrong numbers on Helix_only, Carousel_only,
  Not_placed and Bulk_Routed (those sheets numbered only their own rows); use
  the Result sheet, or reload the run with "Load & recompute" and download it
  again.

## Restocking (machine database)

- A restock stockpile needs both the stockpile's maximum restock amount and the
  article's maximum re-storage quantity set; either alone does nothing.
