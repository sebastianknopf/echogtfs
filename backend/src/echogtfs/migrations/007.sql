-- Migration 007: Add is_active column to data_sources table
-- This allows enabling/disabling data sources without deleting them.
-- When a data source is disabled, its alerts should be deleted.

DO $$
BEGIN
    -- Add is_active column (default TRUE) if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='data_sources' AND column_name='is_active') THEN
        ALTER TABLE data_sources 
            ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END $$;

-- Add index on is_active for efficient filtering
CREATE INDEX IF NOT EXISTS idx_data_sources_is_active ON data_sources(is_active);
