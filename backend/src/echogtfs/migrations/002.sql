-- Migration 002: Add data_sources and data_source_mappings tables
-- Data sources represent external systems with type-specific configuration stored as JSON.
-- Mappings link GTFS entities to arbitrary key-value pairs without foreign key constraints.

CREATE TABLE IF NOT EXISTS data_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(64) NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    cron VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_data_sources_name ON data_sources (name);
CREATE INDEX IF NOT EXISTS ix_data_sources_type ON data_sources (type);

CREATE TABLE IF NOT EXISTS data_source_mappings (
    id SERIAL PRIMARY KEY,
    data_source_id INTEGER NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    key VARCHAR(128) NOT NULL,
    value VARCHAR(512) NOT NULL,
    FOREIGN KEY (data_source_id) REFERENCES data_sources (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_data_source_mappings_data_source_id ON data_source_mappings (data_source_id);
CREATE INDEX IF NOT EXISTS ix_data_source_mappings_entity_type ON data_source_mappings (entity_type);
CREATE INDEX IF NOT EXISTS ix_data_source_mappings_key ON data_source_mappings (key);
CREATE INDEX IF NOT EXISTS ix_data_source_mappings_value ON data_source_mappings (value);
