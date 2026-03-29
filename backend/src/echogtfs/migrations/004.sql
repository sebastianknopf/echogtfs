-- Migration 004: Add CASCADE DELETE to service alert foreign keys
-- This ensures that when a service_alert is deleted, all related translations,
-- active_periods, and informed_entities are automatically deleted as well.
-- Required for bulk delete operations that bypass SQLAlchemy ORM cascade logic.

DO $$
BEGIN
    -- Drop existing constraint if it exists and re-add with ON DELETE CASCADE
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name='service_alert_translations_alert_id_fkey' 
               AND table_name='service_alert_translations') THEN
        ALTER TABLE service_alert_translations 
            DROP CONSTRAINT service_alert_translations_alert_id_fkey;
    END IF;
    
    -- Add constraint with ON DELETE CASCADE if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='service_alert_translations_alert_id_fkey' 
                   AND table_name='service_alert_translations') THEN
        ALTER TABLE service_alert_translations 
            ADD CONSTRAINT service_alert_translations_alert_id_fkey 
            FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;
    END IF;
    
    -- Drop existing constraint if it exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name='service_alert_active_periods_alert_id_fkey' 
               AND table_name='service_alert_active_periods') THEN
        ALTER TABLE service_alert_active_periods 
            DROP CONSTRAINT service_alert_active_periods_alert_id_fkey;
    END IF;
    
    -- Add constraint with ON DELETE CASCADE if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='service_alert_active_periods_alert_id_fkey' 
                   AND table_name='service_alert_active_periods') THEN
        ALTER TABLE service_alert_active_periods 
            ADD CONSTRAINT service_alert_active_periods_alert_id_fkey 
            FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;
    END IF;
    
    -- Drop existing constraint if it exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name='service_alert_informed_entities_alert_id_fkey' 
               AND table_name='service_alert_informed_entities') THEN
        ALTER TABLE service_alert_informed_entities 
            DROP CONSTRAINT service_alert_informed_entities_alert_id_fkey;
    END IF;
    
    -- Add constraint with ON DELETE CASCADE if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='service_alert_informed_entities_alert_id_fkey' 
                   AND table_name='service_alert_informed_entities') THEN
        ALTER TABLE service_alert_informed_entities 
            ADD CONSTRAINT service_alert_informed_entities_alert_id_fkey 
            FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;
    END IF;
END $$;
