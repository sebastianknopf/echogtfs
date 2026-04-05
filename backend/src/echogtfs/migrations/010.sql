-- Migration 010: Add data_source_enrichments table
-- 
-- Enrichments allow extracting cause, effect, and severity from alert text fields.
-- Unlike mappings, enrichments support pattern matching and are sortable by priority.
-- 
-- Features:
--   - enrichment_type: "cause", "effect", or "severity"
--   - source_field: "header", "description", or "header_description" (both)
--   - key: Text or regex pattern to match in the source field
--   - value: The value to assign when matched (e.g., "STRIKE", "NO_SERVICE", "SEVERE")
--   - sort_order: Priority/order of application (lower numbers = higher priority)

CREATE TABLE IF NOT EXISTS data_source_enrichments (
    id SERIAL PRIMARY KEY,
    data_source_id INTEGER NOT NULL,
    enrichment_type VARCHAR(32) NOT NULL,
    source_field VARCHAR(32) NOT NULL,
    key VARCHAR(512) NOT NULL,
    value VARCHAR(128) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (data_source_id) REFERENCES data_sources (id) ON DELETE CASCADE
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS ix_data_source_enrichments_data_source_id 
    ON data_source_enrichments (data_source_id);
CREATE INDEX IF NOT EXISTS ix_data_source_enrichments_enrichment_type 
    ON data_source_enrichments (enrichment_type);
CREATE INDEX IF NOT EXISTS ix_data_source_enrichments_source_field 
    ON data_source_enrichments (source_field);
CREATE INDEX IF NOT EXISTS ix_data_source_enrichments_sort_order 
    ON data_source_enrichments (data_source_id, sort_order);

-- Add constraint to ensure valid enrichment types
DO $$
BEGIN
    -- Only add constraint if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='chk_enrichment_type' 
                   AND table_name='data_source_enrichments') THEN
        ALTER TABLE data_source_enrichments
            ADD CONSTRAINT chk_enrichment_type 
            CHECK (enrichment_type IN ('cause', 'effect', 'severity'));
    END IF;
END $$;

-- Add constraint to ensure valid source fields
DO $$
BEGIN
    -- Only add constraint if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='chk_source_field' 
                   AND table_name='data_source_enrichments') THEN
        ALTER TABLE data_source_enrichments
            ADD CONSTRAINT chk_source_field 
            CHECK (source_field IN ('header', 'description', 'header_description'));
    END IF;
END $$;
