-- Audit M3: the dedup authority queries engine_executions by inputs_hash
-- before archiving; index it so the lookup stays flat as archives grow.
CREATE INDEX IF NOT EXISTS idx_engine_executions_inputs_hash
    ON engine_executions(inputs_hash);
