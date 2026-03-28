-- Migration 003: Add last_run_at column to data_sources table
-- This field tracks when the data source was last executed/synchronized.

ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_data_sources_last_run_at ON data_sources (last_run_at);
