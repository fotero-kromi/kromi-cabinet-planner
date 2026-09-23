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

## Takeover sheets

- Every takeover is customer property. One sheet per supply point.
- Whole packs go into the KTC up to the maximum; the rest stays at the main stock
  location (HLO).
- Maximum: Carousel = compartments x VPE; Helix = spirals x packs per spiral x
  VPE (a regrind article keeps one spiral free). Lockers, Kanban and not-placed
  articles hold nothing in the KTC.
- Replicate mode shares one stock pool across supply points, filled in supply
  point order; with a Program mapping each supply point uses its own stock.
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

## Restocking (machine database)

- A restock stockpile needs both the stockpile's maximum restock amount and the
  article's maximum re-storage quantity set; either alone does nothing.
