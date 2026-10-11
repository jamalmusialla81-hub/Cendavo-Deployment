-- Website enquiries submitted through functions/api/enquiry.js (D1 binding ENQUIRIES_DB).
-- Apply once per database; see docs/ENQUIRIES.md. No IP address or user-agent data is stored, and
-- `budget` is reserved but not collected yet (see "Differences from the task spec" in docs/ENQUIRIES.md).
CREATE TABLE IF NOT EXISTS enquiries (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  business TEXT,
  website TEXT,
  service TEXT NOT NULL,
  budget TEXT,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'qualified', 'closed')),
  idempotency_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS enquiries_status_created ON enquiries (status, created_at);
