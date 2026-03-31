-- Migration 008: Add invalid reference handling and entity validation columns
-- 
-- 1. Add invalid_reference_policy to data_sources table
--    This defines how to handle alerts with invalid entity references.
--    Possible values:
--      - 'discard_alert': Discard the entire alert if any reference is invalid
--      - 'keep_alert': Keep the entire alert even if references are invalid
--      - 'discard_invalid': Discard only invalid references, keep the alert
--      - 'not_specified': No specific policy defined
--
-- 2. Add is_valid to service_alert_informed_entities table
--    This marks whether the entity reference is valid (exists in GTFS data).

DO $$
BEGIN
    -- Add invalid_reference_policy column to data_sources (default: not_specified)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='data_sources' AND column_name='invalid_reference_policy') THEN
        ALTER TABLE data_sources 
            ADD COLUMN invalid_reference_policy VARCHAR(32) NOT NULL DEFAULT 'not_specified';
        
        -- Add check constraint to ensure only valid values are used
        ALTER TABLE data_sources
            ADD CONSTRAINT chk_invalid_reference_policy 
            CHECK (invalid_reference_policy IN ('discard_alert', 'keep_alert', 'discard_invalid', 'not_specified'));
    END IF;
    
    -- Add is_valid column to service_alert_informed_entities (default: TRUE)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='service_alert_informed_entities' AND column_name='is_valid') THEN
        ALTER TABLE service_alert_informed_entities 
            ADD COLUMN is_valid BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END $$;

-- Add index on is_valid for efficient filtering of invalid references
CREATE INDEX IF NOT EXISTS idx_service_alert_informed_entities_is_valid 
    ON service_alert_informed_entities(is_valid);

-- Add index on invalid_reference_policy for efficient filtering
CREATE INDEX IF NOT EXISTS idx_data_sources_invalid_reference_policy 
    ON data_sources(invalid_reference_policy);
