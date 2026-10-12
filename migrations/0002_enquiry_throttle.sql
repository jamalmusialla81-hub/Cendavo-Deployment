-- Indexes for the built-in throttle in functions/api/enquiry.js (20 enquiries per 10 minutes overall,
-- 3 per email address per hour). Apply after 0001; see docs/ENQUIRIES.md. Adds no columns, and still no
-- IP address or user-agent data. IF NOT EXISTS makes a second run harmless.
CREATE INDEX IF NOT EXISTS enquiries_created ON enquiries (created_at);
CREATE INDEX IF NOT EXISTS enquiries_email_created ON enquiries (email, created_at);
