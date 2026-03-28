-- Migration 005: Add data_source_id foreign key to service_alerts
-- This creates a proper relation between data sources and alerts.
-- NULL data_source_id means internal alert (created in echogtfs UI).
-- Non-NULL data_source_id means external alert (imported from data source).

-- Add nullable data_source_id column with foreign key and ON DELETE CASCADE
ALTER TABLE service_alerts 
    ADD COLUMN data_source_id INTEGER;

-- Add foreign key constraint with CASCADE DELETE
-- When a data source is deleted, all its alerts are automatically deleted
ALTER TABLE service_alerts 
    ADD CONSTRAINT service_alerts_data_source_id_fkey 
    FOREIGN KEY (data_source_id) 
    REFERENCES data_sources (id) 
    ON DELETE CASCADE;

-- Add index for better query performance
CREATE INDEX idx_service_alerts_data_source_id 
    ON service_alerts (data_source_id);

-- The 'source' column is kept for backward compatibility and display purposes
-- but the data_source_id is now the authoritative link
