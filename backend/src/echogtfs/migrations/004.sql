-- Migration 004: Add CASCADE DELETE to service alert foreign keys
-- This ensures that when a service_alert is deleted, all related translations,
-- active_periods, and informed_entities are automatically deleted as well.
-- Required for bulk delete operations that bypass SQLAlchemy ORM cascade logic.

-- Drop existing constraints (if they exist)
ALTER TABLE service_alert_translations 
    DROP CONSTRAINT IF EXISTS service_alert_translations_alert_id_fkey;

ALTER TABLE service_alert_active_periods 
    DROP CONSTRAINT IF EXISTS service_alert_active_periods_alert_id_fkey;

ALTER TABLE service_alert_informed_entities 
    DROP CONSTRAINT IF EXISTS service_alert_informed_entities_alert_id_fkey;

-- Re-add constraints with ON DELETE CASCADE
ALTER TABLE service_alert_translations 
    ADD CONSTRAINT service_alert_translations_alert_id_fkey 
    FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;

ALTER TABLE service_alert_active_periods 
    ADD CONSTRAINT service_alert_active_periods_alert_id_fkey 
    FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;

ALTER TABLE service_alert_informed_entities 
    ADD CONSTRAINT service_alert_informed_entities_alert_id_fkey 
    FOREIGN KEY (alert_id) REFERENCES service_alerts (id) ON DELETE CASCADE;
