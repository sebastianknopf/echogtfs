-- Migration 011: Add period_type to service_alert_active_periods
-- 
-- Extends the active_periods model to distinguish between:
--   - impact_period: The actual validity period of the alert (when it affects service)
--   - communication_period: The publication period (when the alert should be shown)
-- 
-- For existing alerts, period_type defaults to 'impact_period' to preserve
-- current behavior and prevent breaking changes.

-- Add the period_type column with default value
DO $$
BEGIN
    -- Only add column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='service_alert_active_periods' 
                   AND column_name='period_type') THEN
        ALTER TABLE service_alert_active_periods
            ADD COLUMN period_type VARCHAR(32) NOT NULL DEFAULT 'impact_period';
    END IF;
END $$;

-- Update existing records to explicitly set impact_period
-- This ensures consistency even if the default changes in the future
UPDATE service_alert_active_periods
SET period_type = 'impact_period'
WHERE period_type IS NULL OR period_type = '';

-- Add constraint to ensure valid period types
DO $$
BEGIN
    -- Only add constraint if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='chk_period_type' 
                   AND table_name='service_alert_active_periods') THEN
        ALTER TABLE service_alert_active_periods
            ADD CONSTRAINT chk_period_type 
            CHECK (period_type IN ('impact_period', 'communication_period'));
    END IF;
END $$;

-- Add index for efficient filtering by period type
CREATE INDEX IF NOT EXISTS ix_service_alert_active_periods_period_type 
    ON service_alert_active_periods (period_type);
