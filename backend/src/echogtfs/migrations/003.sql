-- Migration 003: Add last_run_at column to data_sources table
-- This field tracks when the data source was last executed/synchronized.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='data_sources' AND column_name='last_run_at') THEN
        ALTER TABLE data_sources ADD COLUMN last_run_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_data_sources_last_run_at ON data_sources (last_run_at);
