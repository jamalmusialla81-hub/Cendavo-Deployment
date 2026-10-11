# Lead Hunter plan

**Status (2026-10-11): does not exist.** No code, task or document mentioned it before this file. It is not queued yet so it cannot delay the enquiry workflow (task A).

Purpose: an internal research tool that helps Cendavo find local service businesses that would benefit from a better website. It is separate from the public enquiry form.

## MVP (future Forge task I, profile `app`)

- Input: a category and suburb list (start: 30 mobile detailing businesses in Sydney; later up to 100 across detailing, landscaping, pressure washing, cleaning, barbers).
- Per lead: business name, website URL (or none), public contact channel, category, location, research source URL, last verified date.
- Website quality assessment from the public page only: reachable/HTTPS, mobile viewport, rough load size, contact path, outdated signals. Opportunity score 0–100 with the reasons that produced it.
- Duplicate detection (normalised domain, name + suburb), manual status (`new`, `reviewed`, `contacted`, `not-a-fit`), CSV export.

## Rules

- Research only public information a person could look up; respect `robots.txt` and site terms; no scraping behind logins; no bulk automated requests.
- Never fabricate a lead: every row needs a source URL and verification date.
- No automatic outreach. Any contact is manual and must comply with the Spam Act 2003 (consent, identification, unsubscribe) and the Privacy Act / APPs; store only business contact details.
- Data stays local (not in Git).

## Open questions for the owner

Which data sources are acceptable (manual search export, Google Places API — paid beyond free tier — or a provided list)? Where should research data live?
