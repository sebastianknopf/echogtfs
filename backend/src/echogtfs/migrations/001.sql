-- Migration 001: Add is_technical_contact column to users table
-- This field indicates whether a user serves as a technical contact person.

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_technical_contact BOOLEAN NOT NULL DEFAULT FALSE;
