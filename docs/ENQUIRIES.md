# Website enquiries

The contact page form (`pages/contact.html`, `assets/enquiry.js`) posts JSON to `/api/enquiry`. The Cloudflare Pages Function `functions/api/enquiry.js` validates it again on the server and stores it in a Cloudflare D1 database through the binding `ENQUIRIES_DB`. Nobody is notified: enquiries wait in D1 until the owner reads them (see below).

There is no `wrangler.toml`. The binding is configured in the Cloudflare dashboard so the Git-linked Pages project's settings stay where they are.

## One-time setup (owner)

1. **Create the database.** Cloudflare dashboard → Storage & Databases → D1 → *Create*. Name it, for example, `cendavo-enquiries`. Or from a machine where you are logged in to Wrangler:
   ```sh
   npx wrangler d1 create cendavo-enquiries
   ```
2. **Apply the migration.** In the dashboard open the database → *Console*, paste the contents of `migrations/0001_enquiries.sql` and run it. Or:
   ```sh
   npx wrangler d1 execute cendavo-enquiries --remote --file=migrations/0001_enquiries.sql
   ```
   The migration uses `IF NOT EXISTS`, so running it twice is harmless.
3. **Bind it to the Pages project.** Workers & Pages → `cendavo-deployment` → Settings → Bindings → *Add* → D1 database. Variable name **`ENQUIRIES_DB`**, database `cendavo-enquiries`. Add it for **both Production and Preview**, then redeploy (a new push or *Retry deployment*) so the function picks it up.
4. **Test it.** Send one enquiry from the preview URL and check that exactly one row appears (query below). Pressing submit twice or retrying after a network error must not create a second row.

Until step 3 is done the form answers "Enquiries are temporarily unavailable, so nothing was sent" and keeps everything the visitor typed. The local `python3 -m http.server` preview has no functions at all, so there the form shows its generic "could not be sent" message.

The Git-linked build serves `dist/` and picks up `functions/` from the repository root. If you use the manual GitHub Actions deploy (`wrangler pages deploy dist`, run from the repository root), check once that the deployment lists the `/api/enquiry` function.

## Reading enquiries (read-only)

Dashboard → D1 → `cendavo-enquiries` → Console, or `npx wrangler d1 execute cendavo-enquiries --remote --command "…"`:

```sql
SELECT id, created_at, name, email, phone, business, website, service, message
FROM enquiries
WHERE status = 'new'
ORDER BY created_at;
```

## Updating a status

Allowed values are `new`, `contacted`, `qualified` and `closed` (the database rejects anything else).

```sql
UPDATE enquiries SET status = 'contacted' WHERE id = 42;
```

To delete someone's details on request:

```sql
DELETE FROM enquiries WHERE email = 'person@example.com';
```

## What the endpoint does

| Request | Response |
| --- | --- |
| Not `POST` | `405`, `Allow: POST` |
| Content type not `application/json` | `415` |
| Body over 16 KB (actual bytes, not just `Content-Length`) | `413` |
| `Origin` header from another site | `403` |
| Unreadable or non-object JSON | `400` |
| Honeypot `company_url` filled (checked first) | `200 {ok:true}`, **nothing stored**; a bot sees the same answer as a person |
| `elapsedMs` missing, not a number, or under 800 ms | `429`, `Retry-After: 1`, `{ok:false, retry:true, message}`, **nothing stored**; the form keeps the details and shows "not sent, wait a moment and press send again" |
| A field fails validation | `400 {ok:false, errors:{field: message}}` |
| `ENQUIRIES_DB` not bound | `503`, "nothing was sent, try again later" |
| New enquiry | `201 {ok:true, id}` |
| Same `idempotencyKey` again | `200 {ok:true, id}` with the original id; no second row |
| Database error | `503` with a generic message; error details are never returned |

A repeated key returns the original enquiry even if the later copy's text differs. The browser keeps one key per enquiry, reuses it for retries and creates a new one only after a successful send.

Stored fields: name, email (lower-cased), optional phone, business and website (normalised to a full `https://` address), service, message, status, creation time and the idempotency key. No IP address or user-agent data is stored. The `budget` column exists but the form does not ask for it. See "Differences from the task spec" below.

## Spam and abuse

The honeypot stops simple bots only; anyone can call the endpoint directly. The fill-time check is a weak signal: `elapsedMs` is reported by the browser and is easy to fake, so it is set low (800 ms, faster than anyone can fill the form) and answered with an honest `429` and a visible retry message instead of a fake success, so a real visitor is never told an unsent enquiry was received. The same message appears if a Cloudflare rate limit answers `429`. Each spam rejection logs one fixed line, `enquiry: spam rejected (honeypot)` or `enquiry: spam rejected (timing)`, with no request data, so the owner can count them in the Pages Functions logs. The real defences are the honeypot and a rate limit. Every accepted submission is a D1 write. To limit floods without paid services, add a free **WAF rate-limiting rule** in the Cloudflare dashboard (Security → WAF → Rate limiting rules), for example: URI path equals `/api/enquiry` and method `POST`, at most 5 requests per 10 seconds per IP, action *Block*. Check the current free-plan limits for D1, Functions and rate limiting on the account.

## Differences from the task spec

`docs/CENDAVO_TASK_1_RECOVERY.md` is unchanged. This implementation follows the smaller scope that the Strategist recommended in its report for this Forge task. That report is a Forge run artefact, not a file in this repository, and **these differences are not owner decisions** (`docs/DECISIONS.md` has no entry for them). The owner should confirm or reverse them:

| Spec item | What was built | Why it was recommended |
| --- | --- | --- |
| 1. Optional budget range | Not collected; the nullable `budget` column is kept | Budget ranges would be invented price points, and each extra field costs conversions |
| 4 and 7. Salted `user_agent_hash` | Not stored; no user-agent or IP data is kept | A salt is a secret to manage, the hash does not help qualify a lead, and storing less personal data is safer |
| 6. "please email …" in the 503 message | No email address; the message says nothing was sent and to try again later | No email address is published |
| 1. Business name | Optional | Fewer required fields |
| 9. Demo "Other" fix | No change | Already present before this task (`value="Other"` with a regression test) |
| Additions | Same-origin `Origin` check, collection notice on the form, owner queries in this file | Abuse protection, transparency, leads readable without an admin view |

Reversing the budget or user-agent items later means adding the form field (with owner-chosen ranges) or a salt secret, a migration, and updating `tests/test_enquiry.py`, which currently checks that neither is stored.

## Not built yet

- Notifications (needs an email provider). Check D1 regularly.
- An admin view (needs authentication such as Cloudflare Access).
- A retention rule. Decide how long enquiries are kept and delete older rows by hand until then.
- CAPTCHA (Turnstile needs a site key).
