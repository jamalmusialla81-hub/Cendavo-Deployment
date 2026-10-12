# Website enquiries

The contact page form (`pages/contact.html`, `assets/enquiry.js`) posts JSON to `/api/enquiry`. The Cloudflare Pages Function `functions/api/enquiry.js` validates it again on the server and stores it in a Cloudflare D1 database through the binding `ENQUIRIES_DB`. When the secrets `RESEND_API_KEY` and `ALERT_TO` are set, each new enquiry also sends the owner one plain-text alert email through Resend (see "Email alerts" below). Without them, nobody is notified and enquiries wait in D1 until the owner reads them.

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
   Then apply `migrations/0002_enquiry_throttle.sql` the same way (it adds the two indexes the spam throttle uses):
   ```sh
   npx wrangler d1 execute cendavo-enquiries --remote --file=migrations/0002_enquiry_throttle.sql
   ```
   Both migrations use `IF NOT EXISTS`, so running them twice is harmless.
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
| Same `idempotencyKey` again | `200 {ok:true, id}` with the original id; no second row and no alert. Checked **before** the throttle, so a retry of an enquiry that was already stored is confirmed even when the throttle is full |
| Throttle full: 20 or more enquiries stored in the last 10 minutes, or 3 or more from the same (lower-cased) email address in the last hour | `429`, `Retry-After: 60`, the same `{ok:false, retry:true, message}` as the timing check, **nothing stored**, no alert |
| New enquiry | `201 {ok:true, id}`; then one alert email if alerts are configured |
| Database error | `503` with a generic message; error details are never returned |

A repeated key returns the original enquiry even if the later copy's text differs. The browser keeps one key per enquiry, reuses it for retries and creates a new one only after a successful send.

Stored fields: name, email (lower-cased), optional phone, business and website (normalised to a full `https://` address), service, message, status, creation time and the idempotency key. No IP address or user-agent data is stored. The `budget` column exists but the form does not ask for it. See "Differences from the task spec" below.

## Spam and abuse

The honeypot stops simple bots only; anyone can call the endpoint directly. The fill-time check is a weak signal: `elapsedMs` is reported by the browser and is easy to fake, so it is set low (800 ms, faster than anyone can fill the form) and answered with an honest `429` and a visible retry message instead of a fake success, so a real visitor is never told an unsent enquiry was received. Each spam rejection logs one fixed line, `enquiry: spam rejected (honeypot)` or `enquiry: spam rejected (timing)`, with no request data, so the owner can count them in the Pages Functions logs.

**Built-in throttle.** Cloudflare WAF rate-limiting rules are not available for a `*.pages.dev` address (per the Task 30 plan in `docs/NIGHT_SHIFT_PLAN.md`; not re-checked here), so the function limits floods itself, using only the stored `created_at` and `email` columns (no IP address or user-agent data):

- at most **20 enquiries in any 10 minutes** across the whole site;
- at most **3 enquiries per email address per hour**.

When either limit is reached the visitor gets the same honest `429` retry message as the timing check, nothing is stored and the log shows `enquiry: throttled`. The limits are soft: two requests at the same moment can both pass the check and slightly exceed them. The site-wide limit also means that **a flood blocks real visitors** until it drops out of the 10-minute window; that is the accepted trade-off for a free setup, and the visitor is told plainly that the enquiry was not sent. Someone can avoid the per-email limit by changing addresses, but the site-wide limit still applies. The counts compare ISO timestamps as text, which is only correct because every `created_at` is written in UTC by `toISOString()`; keep it that way if rows are ever added by hand. The indexes are in `migrations/0002_enquiry_throttle.sql`. Check the current free-plan limits for D1 and Functions on the account.

## Email alerts

After a **new** enquiry is stored (the `201` path only), the function sends one email to the owner through [Resend](https://resend.com) (approved by the owner, `docs/DECISIONS.md` decision 008):

- from `Cendavo enquiries <onboarding@resend.dev>` to the address in `ALERT_TO`;
- subject `New enquiry: <name> (<service>)`;
- plain text only (no HTML), listing every stored field and labelled as typed by the visitor and unverified;
- `reply_to` is the visitor's email, so *Reply* goes to them, unless the address contains any of `< > , ; : " ( ) [ ] \`. Then `reply_to` is left out and the address is only in the body.

The email is sent with `waitUntil` after the visitor's response, so it never delays or changes that response. A Resend error, network error or a request that takes longer than 5 seconds (aborted) is ignored apart from one fixed log line, `enquiry: alert email failed`; the API key, Resend's reply and visitor details are never logged or returned. The only outbound request the function makes is to `https://api.resend.com/emails`. No alert is sent for repeats, honeypot hits, rejected or throttled submissions, or database errors.

**Setup (owner):**

1. Sign up at Resend with the inbox that should receive alerts. With the shared `onboarding@resend.dev` test sender, Resend delivers only to the account's own email address (check Resend's current rules), which is why `ALERT_TO` must be that address.
2. Resend → API Keys → *Create API key* with **Sending access**. Copy it once.
3. Cloudflare dashboard → Workers & Pages → `cendavo-deployment` → Settings → Variables and secrets, environment **Production**:
   - `RESEND_API_KEY`: the key, type **Secret** (encrypted);
   - `ALERT_TO`: the Resend account's email address.
4. Redeploy (*Retry deployment* or a new push) so the function picks them up.
5. Send one enquiry from the live site. Exactly one alert should arrive; check the spam folder and add a filter or allow-list entry if needed, and check that *Reply* goes to the visitor. Sending the same enquiry again (same key) must not send a second email.

If either secret is missing or empty, alerts are skipped silently and enquiries are only stored. Secrets set for Production only are not available to Preview deployments, so previews store enquiries without alerting; that is intended. Check Resend's current free-tier sending limits and how long it keeps message logs, because each alert copies the enquiry to Resend and to the owner's inbox (the form's privacy notice says so).

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

- An admin view (needs authentication such as Cloudflare Access).
- A retention rule. Decide how long enquiries are kept and delete older rows by hand until then.
- CAPTCHA (Turnstile needs a site key).
