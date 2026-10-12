// Cloudflare Pages Function: POST /api/enquiry stores a website enquiry in D1 (binding ENQUIRIES_DB) and,
// when the secrets RESEND_API_KEY and ALERT_TO are set, emails the owner a plain-text alert after the response.
// The validation rules and messages below are mirrored in assets/enquiry.js; tests/test_enquiry.py
// runs one shared case table against both so they cannot drift apart.

export const MAX_BODY_BYTES = 16 * 1024;
// Weak spam signal only: a submission reporting less than this is refused with a visible retry.
export const MIN_FILL_MS = 800;
export const SERVICES = ['website-design', 'website-redesign', 'maintenance', 'not-sure'];

export const MESSAGES = {
  name: 'Enter your name (up to 100 characters).',
  email: 'Enter a valid email address, like name@example.com.',
  phone: 'Enter a phone number using digits, spaces and + ( ) - only (up to 30 characters).',
  business: 'Keep the business name to 120 characters or fewer.',
  website: 'Enter a website address, like example.com.au (up to 200 characters).',
  service: 'Choose the service you are interested in.',
  message: 'Tell us a little about your project (10 to 2000 characters).',
  idempotencyKey: 'Please reload the page and try again.',
};

const UNAVAILABLE = 'Enquiries are temporarily unavailable, so nothing was sent. Please try again later.';
const RETRY = 'Your enquiry was not sent. Please wait a moment and send it again.';
const NOT_CONFIRMED = 'We could not confirm your enquiry. Please try again in a few minutes.';

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE = /^[0-9+() -]+$/;
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// Strings only; anything else becomes null (invalid). Single-line fields collapse whitespace and
// control characters to one space; the message keeps line breaks but drops other control characters.
function clean(value, multiline) {
  if (value === undefined || value === null) return '';
  if (typeof value !== 'string') return null;
  if (multiline) {
    return value.replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').trim();
  }
  return value.replace(/[\s\u0000-\u001f\u007f]+/g, ' ').trim();
}

function normaliseWebsite(value) {
  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : 'https://' + value;
  let url;
  try {
    url = new URL(candidate);
  } catch {
    return null;
  }
  if ((url.protocol !== 'http:' && url.protocol !== 'https:') || url.username || url.password || !url.hostname.includes('.')) return null;
  return url.href.length <= 200 ? url.href : null;
}

export function validateEnquiry(input) {
  const source = input && typeof input === 'object' && !Array.isArray(input) ? input : {};
  const errors = {};
  const values = {};

  const name = clean(source.name);
  if (!name || name.length > 100) errors.name = MESSAGES.name;
  else values.name = name;

  const email = clean(source.email);
  if (!email || email.length > 254 || !EMAIL.test(email)) errors.email = MESSAGES.email;
  else values.email = email.toLowerCase();

  const phone = clean(source.phone);
  if (phone === null || (phone && (phone.length > 30 || !PHONE.test(phone) || !/[0-9]/.test(phone)))) errors.phone = MESSAGES.phone;
  else values.phone = phone || null;

  const business = clean(source.business);
  if (business === null || business.length > 120) errors.business = MESSAGES.business;
  else values.business = business || null;

  const website = clean(source.website);
  if (website === null || website.length > 200) errors.website = MESSAGES.website;
  else if (website) {
    const href = normaliseWebsite(website);
    if (href) values.website = href;
    else errors.website = MESSAGES.website;
  } else values.website = null;

  const service = clean(source.service);
  if (!SERVICES.includes(service)) errors.service = MESSAGES.service;
  else values.service = service;

  const message = clean(source.message, true);
  if (!message || message.length < 10 || message.length > 2000) errors.message = MESSAGES.message;
  else values.message = message;

  const key = clean(source.idempotencyKey);
  if (!key || !UUID_V4.test(key.toLowerCase())) errors.idempotencyKey = MESSAGES.idempotencyKey;
  else values.idempotencyKey = key.toLowerCase();

  return { valid: Object.keys(errors).length === 0, values, errors };
}

function json(status, body, extraHeaders) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
      ...extraHeaders,
    },
  });
}

// Reads at most MAX_BODY_BYTES actual bytes; returns null as soon as the body is larger.
async function readLimitedBody(request) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) {
      await reader.cancel().catch(() => {});
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

const INSERT_SQL =
  'INSERT INTO enquiries (created_at, name, email, phone, business, website, service, message, idempotency_key) ' +
  'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING RETURNING id';
const SELECT_SQL = 'SELECT id FROM enquiries WHERE idempotency_key = ?';

// Built-in throttle (soft: concurrent requests can slightly exceed it). Cutoffs are ISO strings bound as
// parameters; this only works because every created_at is written by toISOString() in UTC.
// Indexes: migrations/0002_enquiry_throttle.sql.
export const THROTTLE = { globalLimit: 20, globalWindowMs: 10 * 60 * 1000, emailLimit: 3, emailWindowMs: 60 * 60 * 1000 };
const THROTTLE_SQL =
  'SELECT (SELECT COUNT(*) FROM enquiries WHERE created_at > ?) AS recent, ' +
  '(SELECT COUNT(*) FROM enquiries WHERE email = ? AND created_at > ?) AS recent_email';

// Alert email to the owner through Resend. The URL is fixed; nothing else is ever fetched.
const RESEND_URL = 'https://api.resend.com/emails';
const ALERT_FROM = 'Cendavo enquiries <onboarding@resend.dev>';
export const ALERT_TIMEOUT_MS = 5000;
const ALERT_FAILED = 'enquiry: alert email failed';
// reply_to is only set for addresses that cannot carry a display name or a second address.
const REPLY_TO_UNSAFE = /[<>,;:"()[\]\\]/;

function alertText(values, id, createdAt) {
  const shown = value => value || '(not given)';
  return [
    'A new enquiry was submitted through the website contact form.',
    'Everything below was typed by the visitor and is unverified. Do not open links you do not trust.',
    '',
    `Enquiry id: ${id}`,
    `Received (UTC): ${createdAt}`,
    `Name: ${values.name}`,
    `Email: ${values.email}`,
    `Phone: ${shown(values.phone)}`,
    `Business: ${shown(values.business)}`,
    `Website: ${shown(values.website)}`,
    `Service: ${values.service}`,
    '',
    'Message:',
    values.message,
  ].join('\n');
}

export function buildAlert(values, id, createdAt, alertTo) {
  const email = {
    from: ALERT_FROM,
    to: [alertTo],
    subject: `New enquiry: ${values.name} (${values.service})`,
    text: alertText(values, id, createdAt),
  };
  if (!REPLY_TO_UNSAFE.test(values.email)) email.reply_to = values.email;
  return email;
}

// Never throws and never logs anything but one fixed string: no key, visitor data or Resend reply.
async function sendAlert(env, values, id, createdAt) {
  const controller = new AbortController();
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new Error('timeout'));
    }, ALERT_TIMEOUT_MS);
  });
  try {
    const response = await Promise.race([
      fetch(RESEND_URL, {
        method: 'POST',
        headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, 'content-type': 'application/json' },
        body: JSON.stringify(buildAlert(values, id, createdAt, env.ALERT_TO)),
        signal: controller.signal,
      }),
      timeout,
    ]);
    if (!response || !response.ok) console.error(ALERT_FAILED);
    if (response && response.body && typeof response.body.cancel === 'function') await response.body.cancel().catch(() => {});
  } catch {
    console.error(ALERT_FAILED);
  } finally {
    clearTimeout(timer);
  }
}

// Runs after the response through waitUntil, so the visitor's answer never waits for or depends on it.
function scheduleAlert(context, values, id, createdAt) {
  const env = context.env;
  const configured = env && typeof env.RESEND_API_KEY === 'string' && env.RESEND_API_KEY && typeof env.ALERT_TO === 'string' && env.ALERT_TO;
  if (!configured) return;
  const task = sendAlert(env, values, id, createdAt).catch(() => {});
  try {
    if (typeof context.waitUntil === 'function') context.waitUntil(task);
  } catch {
    // Without waitUntil the send may be cut short, but it can never affect the response.
  }
}

async function handlePost(context) {
  const { request, env } = context;
  const contentType = (request.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
  if (contentType !== 'application/json') return json(415, { ok: false, message: 'Send the enquiry as JSON.' });

  const declared = Number(request.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) return json(413, { ok: false, message: 'The enquiry is too large.' });

  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return json(403, { ok: false, message: 'Cross-site submissions are not accepted.' });

  const bytes = await readLimitedBody(request);
  if (bytes === null) return json(413, { ok: false, message: 'The enquiry is too large.' });

  let body;
  try {
    body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    return json(400, { ok: false, message: 'The enquiry could not be read.' });
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) return json(400, { ok: false, message: 'The enquiry could not be read.' });

  // Spam checks. The honeypot is the real signal: a filled hidden field gets the same success shape a
  // person gets and nothing is stored. Timing is only a weak signal (the browser reports it), so a
  // too-fast or missing elapsedMs is refused honestly with a retry, never a fake success.
  // Logs carry a fixed string only, never request data.
  const honeypot = body.company_url;
  const elapsed = body.elapsedMs;
  if ((typeof honeypot === 'string' && honeypot.trim() !== '') || (honeypot !== undefined && honeypot !== null && typeof honeypot !== 'string')) {
    console.warn('enquiry: spam rejected (honeypot)');
    return json(200, { ok: true });
  }
  if (typeof elapsed !== 'number' || !Number.isFinite(elapsed) || elapsed < MIN_FILL_MS) {
    console.warn('enquiry: spam rejected (timing)');
    return json(429, { ok: false, retry: true, message: RETRY }, { 'retry-after': '1' });
  }

  const { valid, values, errors } = validateEnquiry(body);
  if (!valid) return json(400, { ok: false, errors });

  const db = env && env.ENQUIRIES_DB;
  if (!db || typeof db.prepare !== 'function') return json(503, { ok: false, message: UNAVAILABLE });

  try {
    // A repeat of a stored enquiry is answered before the throttle, so a retry is never told "not sent".
    const stored = await db.prepare(SELECT_SQL).bind(values.idempotencyKey).first();
    if (stored && stored.id != null) return json(200, { ok: true, id: stored.id });

    const now = Date.now();
    const counts = await db
      .prepare(THROTTLE_SQL)
      .bind(new Date(now - THROTTLE.globalWindowMs).toISOString(), values.email, new Date(now - THROTTLE.emailWindowMs).toISOString())
      .first();
    if (counts && (Number(counts.recent) >= THROTTLE.globalLimit || Number(counts.recent_email) >= THROTTLE.emailLimit)) {
      console.warn('enquiry: throttled');
      return json(429, { ok: false, retry: true, message: RETRY }, { 'retry-after': '60' });
    }

    const createdAt = new Date(now).toISOString();
    const inserted = await db
      .prepare(INSERT_SQL)
      .bind(createdAt, values.name, values.email, values.phone, values.business, values.website, values.service, values.message, values.idempotencyKey)
      .first();
    if (inserted && inserted.id != null) {
      scheduleAlert(context, values, inserted.id, createdAt);
      return json(201, { ok: true, id: inserted.id });
    }
    const existing = await db.prepare(SELECT_SQL).bind(values.idempotencyKey).first();
    if (existing && existing.id != null) return json(200, { ok: true, id: existing.id });
    return json(503, { ok: false, message: NOT_CONFIRMED });
  } catch (error) {
    // Log the error type only; never echo database details to the visitor.
    console.error('enquiry: database write failed', error && error.name);
    return json(503, { ok: false, message: NOT_CONFIRMED });
  }
}

// One handler for every method so the 405 holds however Pages orders method-specific routes.
export async function onRequest(context) {
  const { request } = context;
  if (request.method !== 'POST') {
    return json(405, { ok: false, message: 'Use POST to send an enquiry.' }, { allow: 'POST' });
  }
  try {
    return await handlePost(context);
  } catch (error) {
    console.error('enquiry: unexpected failure', error && error.name);
    return json(500, { ok: false, message: NOT_CONFIRMED });
  }
}

export const onRequestPost = onRequest;
