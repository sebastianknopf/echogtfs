-- Migration 009: Extend invalid_reference_policy with discard_invalid_elements option
-- 
-- Adds the 'discard_invalid_elements' policy option, which removes individual
-- invalid fields (agency_id, route_id, stop_id) from informed entities while
-- keeping the entity if at least one valid reference remains.
--
-- Policy values after this migration:
--   - 'discard_alert': Discard the entire alert if any reference is invalid
--   - 'keep_alert': Keep the entire alert even if references are invalid, but deactivate
--   - 'discard_invalid': Discard entire informed entities with invalid references
--   - 'discard_invalid_elements': Discard only invalid fields within entities
--   - 'not_specified': No specific policy defined

DO $$
BEGIN
    -- Drop the old constraint if it exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name='chk_invalid_reference_policy' 
               AND table_name='data_sources') THEN
        ALTER TABLE data_sources DROP CONSTRAINT chk_invalid_reference_policy;
    END IF;
    
    -- Add the new constraint with the additional value
    ALTER TABLE data_sources
        ADD CONSTRAINT chk_invalid_reference_policy 
        CHECK (invalid_reference_policy IN (
            'discard_alert', 
            'keep_alert', 
            'discard_invalid', 
            'discard_invalid_elements',
            'not_specified'
        ));
END $$;
