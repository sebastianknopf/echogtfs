-- Migration 006: Change start_time and end_time to BIGINT in service_alert_active_periods
-- This fixes the issue where timestamps beyond year 2038 cannot be stored in INTEGER (int32).
-- BIGINT (int64) supports timestamps up to year 292,277,026,596 (far into the future).

-- Change start_time from INTEGER to BIGINT
ALTER TABLE service_alert_active_periods 
    ALTER COLUMN start_time TYPE BIGINT;

-- Change end_time from INTEGER to BIGINT
ALTER TABLE service_alert_active_periods 
    ALTER COLUMN end_time TYPE BIGINT;
