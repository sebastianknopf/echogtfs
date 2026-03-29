-- Migration 005: Add data_source_id foreign key to service_alerts
-- This creates a proper relation between data sources and alerts.
-- NULL data_source_id means internal alert (created in echogtfs UI).
-- Non-NULL data_source_id means external alert (imported from data source).

DO $$
BEGIN
    -- Add nullable data_source_id column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='service_alerts' AND column_name='data_source_id') THEN
        ALTER TABLE service_alerts ADD COLUMN data_source_id INTEGER;
    END IF;
    
    -- Add foreign key constraint with CASCADE DELETE if it doesn't exist
    -- When a data source is deleted, all its alerts are automatically deleted
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='service_alerts_data_source_id_fkey' 
                   AND table_name='service_alerts') THEN
        ALTER TABLE service_alerts 
            ADD CONSTRAINT service_alerts_data_source_id_fkey 
            FOREIGN KEY (data_source_id) 
            REFERENCES data_sources (id) 
            ON DELETE CASCADE;
    END IF;
END $$;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_service_alerts_data_source_id 
    ON service_alerts (data_source_id);

-- The 'source' column is kept for backward compatibility and display purposes
-- but the data_source_id is now the authoritative link
