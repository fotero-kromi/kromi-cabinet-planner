-- Restocking persistence (v34.27). Per-row restock decision and the
-- reserved buffer slot count, so the archived record carries what the
-- plan reserved. Fresh databases per version make this a plain widening;
-- old rows read as NULL, which the loaders treat as zero.
ALTER TABLE cabinet_calculations ADD COLUMN restockable INTEGER;
ALTER TABLE cabinet_calculations ADD COLUMN restock_slots INTEGER;
