-- Migration 007: Add is_active column to data_sources table
-- This allows enabling/disabling data sources without deleting them.
-- When a data source is disabled, its alerts should be deleted.

-- Add is_active column (default TRUE)
ALTER TABLE data_sources 
    ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Add index on is_active for efficient filtering
CREATE INDEX idx_data_sources_is_active ON data_sources(is_active);
