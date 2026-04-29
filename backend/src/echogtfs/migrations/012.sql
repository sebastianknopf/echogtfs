-- Migration 012: Add data_source_logs table for external data source request logging
-- 
-- Creates a table to track HTTP requests to external data sources.
-- Metadata (headers, URL, status) is stored in the database.
-- Actual response dumps are stored as files referenced by UUID.
-- Logs are cascade-deleted when the parent data source is deleted.

-- Create the data_source_logs table
CREATE TABLE IF NOT EXISTS data_source_logs (
    id SERIAL PRIMARY KEY,
    data_source_id INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    request_url VARCHAR(2048) NOT NULL,
    request_headers TEXT,
    response_headers TEXT,
    response_mimetype VARCHAR(255),
    status_code INTEGER,
    response_size BIGINT,
    log_file_uuid UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add foreign key constraint with CASCADE DELETE
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name='fk_data_source_logs_data_source_id' 
        AND table_name='data_source_logs'
    ) THEN
        ALTER TABLE data_source_logs
            ADD CONSTRAINT fk_data_source_logs_data_source_id 
            FOREIGN KEY (data_source_id) 
            REFERENCES data_sources(id) 
            ON DELETE CASCADE;
    END IF;
END $$;

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS ix_data_source_logs_data_source_id 
    ON data_source_logs (data_source_id);

CREATE INDEX IF NOT EXISTS ix_data_source_logs_timestamp 
    ON data_source_logs (timestamp);

CREATE INDEX IF NOT EXISTS ix_data_source_logs_log_file_uuid 
    ON data_source_logs (log_file_uuid);
