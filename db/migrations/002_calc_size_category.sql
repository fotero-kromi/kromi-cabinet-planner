-- 002_calc_size_category.sql
-- The result a run delivers shows each tool's size and product category, which a
-- technician override or manual fix can change for that run. tool_classifications
-- holds what the AI or heuristic decided (kept per file, reused across runs);
-- cabinet_calculations holds the value the run used. These two can
-- differ, so the run-effective size and category live on the calculation row to
-- let a reload restore the exact delivered result.

ALTER TABLE cabinet_calculations ADD COLUMN size_category TEXT;
ALTER TABLE cabinet_calculations ADD COLUMN product_category TEXT;
