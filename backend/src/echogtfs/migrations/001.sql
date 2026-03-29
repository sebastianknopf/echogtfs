-- Migration 001: Add is_technical_contact column to users table
-- This field indicates whether a user serves as a technical contact person.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='users' AND column_name='is_technical_contact') THEN
        ALTER TABLE users ADD COLUMN is_technical_contact BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;
