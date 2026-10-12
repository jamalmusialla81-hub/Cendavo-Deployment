"""Enquiry workflow: Pages Function, D1 schema, browser script and contact page.

The function is an ES module, so it is copied into a temporary directory as .mjs and imported with Node;
the browser script is a classic script loaded with require(). Both run the same validation case table.
"""
import functools
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNCTION = ROOT / 'functions' / 'api' / 'enquiry.js'
CLIENT = ROOT / 'assets' / 'enquiry.js'
MIGRATION = ROOT / 'migrations' / '0001_enquiries.sql'
THROTTLE_MIGRATION = ROOT / 'migrations' / '0002_enquiry_throttle.sql'

KEY = '3f2b8c1e-9a4d-4e7b-8c2f-1a2b3c4d5e6f'
VALID = {
    'name': 'Sam Example',
    'email': 'Sam@Example.com',
    'phone': '+61 (2) 5550-0000',
    'business': 'Example Cleaning Co',
    'website': 'example.com.au',
    'service': 'website-redesign',
    'message': 'We need a clearer site that explains our services.',
    'idempotencyKey': KEY,
}

# Shared validation table: (label, overrides, expected error keys). Run against client and server.
CASES = [
    ('valid', {}, []),
    ('valid minimal', {'phone': '', 'business': '', 'website': ''}, []),
    ('valid absent optionals', {'phone': None, 'business': None, 'website': None}, []),
    ('valid http url', {'website': 'http://example.org/path'}, []),
    ('name missing', {'name': '   '}, ['name']),
    ('name too long', {'name': 'a' * 101}, ['name']),
    ('name not a string', {'name': 42}, ['name']),
    ('email missing', {'email': ''}, ['email']),
    ('email no at', {'email': 'sam.example.com'}, ['email']),
    ('email no domain dot', {'email': 'sam@example'}, ['email']),
    ('email too long', {'email': 'a' * 250 + '@x.io'}, ['email']),
    ('phone letters', {'phone': '0400 CALL ME'}, ['phone']),
    ('phone too long', {'phone': '1' * 31}, ['phone']),
    ('phone no digits', {'phone': '()-'}, ['phone']),
    ('business too long', {'business': 'b' * 121}, ['business']),
    ('website javascript', {'website': 'javascript:alert(1)'}, ['website']),
    ('website ftp', {'website': 'ftp://example.com'}, ['website']),
    ('website credentials', {'website': 'https://user:pw@example.com'}, ['website']),
    ('website no dot', {'website': 'localhost'}, ['website']),
    ('website too long', {'website': 'https://example.com/' + 'p' * 190}, ['website']),
    ('service unknown', {'service': 'seo'}, ['service']),
    ('service missing', {'service': ''}, ['service']),
    ('message too short', {'message': 'Hi there'}, ['message']),
    ('message too long', {'message': 'm' * 2001}, ['message']),
    ('key missing', {'idempotencyKey': ''}, ['idempotencyKey']),
    ('key not v4', {'idempotencyKey': '3f2b8c1e-9a4d-1e7b-8c2f-1a2b3c4d5e6f'}, ['idempotencyKey']),
    ('several', {'name': '', 'email': 'x', 'service': 'nope'}, ['email', 'name', 'service']),
]

SERVER_SCRIPT = r"""
const mod = await import(process.argv[2]);
const cases = JSON.parse(process.argv[3]);
const VALID = JSON.parse(process.argv[4]);
const SECRET = 'D1_ERROR: no such table enquiries_secret_internal';

class FakeD1 {
  constructor(opts = {}) { this.rows = []; this.calls = []; this.fail = !!opts.fail; }
  prepare(sql) {
    const db = this;
    const stmt = { sql, args: [],
      bind(...args) { return { ...stmt, args }; },
      async first() { return db.exec(this.sql, this.args); },
      async run() { return db.exec(this.sql, this.args); },
      async all() { return { results: [await db.exec(this.sql, this.args)].filter(Boolean) }; } };
    return stmt;
  }
  async exec(sql, args) {
    this.calls.push({ sql, args });
    if (this.fail) throw new Error(SECRET);
    const insert = /^INSERT INTO enquiries \(([^)]+)\)/.exec(sql);
    if (insert) {
      const cols = insert[1].split(',').map(c => c.trim());
      const row = Object.fromEntries(cols.map((c, i) => [c, args[i]]));
      if (this.rows.some(r => r.idempotency_key === row.idempotency_key)) return null;
      row.id = this.rows.length + 1;
      this.rows.push(row);
      return { id: row.id };
    }
    if (/^SELECT id FROM enquiries WHERE idempotency_key = \?$/.test(sql)) {
      const row = this.rows.find(r => r.idempotency_key === args[0]);
      return row ? { id: row.id } : null;
    }
    if (/^SELECT \(SELECT COUNT\(\*\) FROM enquiries WHERE created_at > \?\) AS recent, \(SELECT COUNT\(\*\) FROM enquiries WHERE email = \? AND created_at > \?\) AS recent_email$/.test(sql)) {
      return { recent: this.rows.filter(r => r.created_at > args[0]).length,
               recent_email: this.rows.filter(r => r.email === args[1] && r.created_at > args[2]).length };
    }
    throw new Error('unexpected SQL ' + sql);
  }
  // Earlier enquiries, ageMs old, written the way the function writes created_at.
  seed(count, { email = null, ageMs = 60 * 1000 } = {}) {
    for (let i = 0; i < count; i++) {
      const id = this.rows.length + 1;
      this.rows.push({ id, created_at: new Date(Date.now() - ageMs).toISOString(), email: email || `other-${id}@example.org`,
                       idempotency_key: `seed-${id}` });
    }
    return this;
  }
  inserts() { return this.calls.filter(c => c.sql.startsWith('INSERT')).length; }
}

// Every outbound request is recorded; the default answer is a Resend-style success.
const fetches = [];
let fetchImpl = async () => new Response('{"id":"resend-test"}', { status: 200 });
globalThis.fetch = async (url, init) => {
  fetches.push({ url: String(url), method: init && init.method, headers: init && init.headers, body: init && init.body ? JSON.parse(init.body) : null,
                 signal: !!(init && init.signal) });
  return fetchImpl(url, init);
};

const URL_ = 'https://cendavo.example/api/enquiry';
function req(body, { method = 'POST', type = 'application/json', headers = {} } = {}) {
  const init = { method, headers: { ...(type ? { 'content-type': type } : {}), ...headers } };
  if (body !== undefined && method !== 'GET' && method !== 'HEAD') init.body = typeof body === 'string' ? body : JSON.stringify(body);
  return new Request(URL_, init);
}
const human = extra => ({ ...VALID, elapsedMs: 8000, ...extra });
async function call(request, env, { waitUntil = true } = {}) {
  const pending = [];
  const context = { request, env };
  if (waitUntil) context.waitUntil = p => { pending.push(p); };
  const res = await mod.onRequest(context);
  const text = await res.text();
  let body = null; try { body = JSON.parse(text); } catch {}
  // Background work must settle (success, failure or timeout) and must never reject.
  const settled = await Promise.allSettled(pending);
  return { status: res.status, body, text, allow: res.headers.get('allow'), type: res.headers.get('content-type'), cache: res.headers.get('cache-control'), retryAfter: res.headers.get('retry-after'),
           headers: [...res.headers], waited: pending.length, rejected: settled.filter(s => s.status === 'rejected').length };
}

const out = {};
out.validation = cases.map(([label, overrides]) => {
  const r = mod.validateEnquiry({ ...VALID, ...overrides });
  return { label, valid: r.valid, keys: Object.keys(r.errors).sort(), values: r.values, errors: r.errors };
});

let db = new FakeD1();
out.created = await call(req(human()), { ENQUIRIES_DB: db });
out.createdRows = structuredClone(db.rows);
out.createdCalls = structuredClone(db.calls);
out.repeat = await call(req(human({ message: 'A second press of the same submit button.' })), { ENQUIRIES_DB: db });
out.repeatRows = db.rows.length;
out.allCalls = structuredClone(db.calls);
out.newKey = await call(req(human({ idempotencyKey: '0a1b2c3d-4e5f-4a6b-9c8d-7e6f5a4b3c2d' })), { ENQUIRIES_DB: db });
out.newKeyRows = db.rows.length;
out.upperKey = await call(req(human({ idempotencyKey: KEY_UPPER })), { ENQUIRIES_DB: db });
out.upperKeyRows = db.rows.length;

out.invalid = {};
for (const [label, overrides, expected] of cases.filter(c => c[2].length)) {
  db = new FakeD1();
  const r = await call(req(human(overrides)), { ENQUIRIES_DB: db });
  out.invalid[label] = { status: r.status, keys: Object.keys((r.body && r.body.errors) || {}).sort(), calls: db.calls.length };
}

const big = JSON.stringify(human({ message: 'x'.repeat(1990), pad: 'p'.repeat(17000) }));
db = new FakeD1();
out.oversize = { ...(await call(req(big), { ENQUIRIES_DB: db })), calls: db.calls.length };
out.oversizeBytes = Buffer.byteLength(big);
const stream = new ReadableStream({ start(c) { for (let i = 0; i < 20; i++) c.enqueue(new TextEncoder().encode('x'.repeat(1024))); c.close(); } });
out.oversizeStream = await call(new Request(URL_, { method: 'POST', headers: { 'content-type': 'application/json' }, body: stream, duplex: 'half' }), { ENQUIRIES_DB: new FakeD1() });
out.declaredOversize = await call(req(human(), { headers: { 'content-length': '999999' } }), { ENQUIRIES_DB: new FakeD1() });
const multibyte = JSON.stringify(human({ pad: '\u20ac'.repeat(5500) }));
out.multibyte = { chars: multibyte.length, bytes: Buffer.byteLength(multibyte), ...(await call(req(multibyte), { ENQUIRIES_DB: new FakeD1() })) };

out.wrongType = await call(req(human(), { type: 'text/plain' }), { ENQUIRIES_DB: new FakeD1() });
out.formType = await call(req('name=x', { type: 'application/x-www-form-urlencoded' }), { ENQUIRIES_DB: new FakeD1() });
out.jsonCharset = await call(req(human({ idempotencyKey: '9e8d7c6b-5a49-4382-a716-151413121110' }), { type: 'Application/JSON; charset=utf-8' }), { ENQUIRIES_DB: new FakeD1() });
out.badJson = await call(req('{"name":'), { ENQUIRIES_DB: new FakeD1() });
out.arrayJson = await call(req('[1,2]'), { ENQUIRIES_DB: new FakeD1() });
out.badUtf8 = await call(new Request(URL_, { method: 'POST', headers: { 'content-type': 'application/json' }, body: new Uint8Array([0x7b, 0xff, 0x7d]) }), { ENQUIRIES_DB: new FakeD1() });
out.foreignOrigin = await call(req(human(), { headers: { origin: 'https://evil.example' } }), { ENQUIRIES_DB: new FakeD1() });
out.nullOrigin = await call(req(human(), { headers: { origin: 'null' } }), { ENQUIRIES_DB: new FakeD1() });
out.sameOrigin = await call(req(human(), { headers: { origin: 'https://cendavo.example' } }), { ENQUIRIES_DB: new FakeD1() });

const warnings = [];
const realWarn = console.warn;
console.warn = (...args) => { warnings.push(args.map(String).join(' ')); };
out.bots = {};
for (const [label, extra] of [
  ['honeypot', { company_url: 'https://spam.example' }],
  ['honeypot non-string', { company_url: 1 }],
  ['honeypot with invalid fields', { company_url: 'x', email: 'bad' }],
  ['honeypot and too fast', { company_url: 'https://spam.example', elapsedMs: 100 }],
  ['honeypot and no timing', { company_url: 'https://spam.example', elapsedMs: undefined }],
]) {
  db = new FakeD1();
  const r = await call(req(human(extra)), { ENQUIRIES_DB: db });
  out.bots[label] = { status: r.status, body: r.body, calls: db.calls.length };
}
out.tooFast = {};
for (const [label, extra] of [
  ['no timing', { elapsedMs: undefined }],
  ['timing as string', { elapsedMs: '9000' }],
  ['timing null (NaN in JSON)', { elapsedMs: NaN }],
  ['799 ms', { elapsedMs: 799 }],
  ['negative', { elapsedMs: -5 }],
  ['zero', { elapsedMs: 0 }],
  ['invalid fields too', { elapsedMs: 100, email: 'bad' }],
]) {
  db = new FakeD1();
  const r = await call(req(human(extra)), { ENQUIRIES_DB: db });
  out.tooFast[label] = { status: r.status, body: r.body, retryAfter: r.retryAfter, cache: r.cache, type: r.type, calls: db.calls.length };
}
out.spamWarnings = warnings.slice();
console.warn = realWarn;
out.humanTiming = {};
for (const ms of [800, 1200]) {
  db = new FakeD1();
  const r = await call(req(human({ elapsedMs: ms })), { ENQUIRIES_DB: db });
  out.humanTiming[ms] = { status: r.status, calls: db.calls.length };
}
db = new FakeD1();
out.blankHoneypot = { ...(await call(req(human({ company_url: '  ' })), { ENQUIRIES_DB: db })), calls: db.calls.length };

db = new FakeD1();
out.budgetIgnored = { ...(await call(req(human({ budget: 'A$5,000+', user_agent: 'x' })), { ENQUIRIES_DB: db })), calls: structuredClone(db.calls), rows: structuredClone(db.rows) };
out.noBinding = await call(req(human()), {});
out.noEnv = await call(req(human()), undefined);
out.invalidBeatsNoBinding = await call(req(human({ email: 'x' })), {});
db = new FakeD1({ fail: true });
out.dbFail = { ...(await call(req(human()), { ENQUIRIES_DB: db })), calls: db.calls.length };
out.secret = SECRET;
// Nothing above configures alerts, so nothing above may reach the network.
out.fetchesWithoutSecrets = fetches.length;

// ---- Alerts (Resend) ----
const API_KEY = 're_test_SECRET_KEY_9f8e7d';
const ALERT_TO = 'owner@example.net';
const RESEND_REPLY = '{"message":"invalid key for sam@example.com","name":"validation_error"}';
const alerting = (db, extra) => ({ ENQUIRIES_DB: db, RESEND_API_KEY: API_KEY, ALERT_TO, ...extra });
const logs = [];
const realConsole = {};
for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
  realConsole[level] = console[level];
  console[level] = (...args) => { logs.push(args.map(String).join(' ')); };
}
const sentFrom = start => structuredClone(fetches.slice(start));

let mark = fetches.length;
db = new FakeD1();
out.alertCreated = await call(req(human()), alerting(db));
out.alertFetches = sentFrom(mark);

out.replyTo = {};
for (const [label, email] of [['plain', 'jo.smith+quotes@example.com.au'], ['angle brackets', '<x@evil.com>'],
                              ['comma', 'a,b@c.d'], ['semicolon', 'a;b@c.d'], ['quote', '"a"@c.d'], ['backslash', 'a\\b@c.d'],
                              ['colon', 'a:b@c.d'], ['parentheses', 'a(b)@c.d'], ['square brackets', 'a[b]@c.d']]) {
  mark = fetches.length;
  db = new FakeD1();
  const r = await call(req(human({ email })), alerting(db));
  const sent = sentFrom(mark);
  out.replyTo[label] = { status: r.status, fetches: sent.length, hasReplyTo: sent.length ? 'reply_to' in sent[0].body : null,
                         replyTo: sent.length ? sent[0].body.reply_to : null, text: sent.length ? sent[0].body.text : null };
}

// Paths that must never send an alert, even with alerts configured.
out.noAlert = {};
async function noAlert(label, run) {
  const start = fetches.length;
  const r = await run();
  out.noAlert[label] = { status: r.status, fetches: fetches.length - start, waited: r.waited };
}
db = new FakeD1();
await call(req(human()), alerting(db));
await noAlert('repeat', () => call(req(human()), alerting(db)));
await noAlert('honeypot', () => call(req(human({ company_url: 'x' })), alerting(new FakeD1())));
await noAlert('invalid', () => call(req(human({ email: 'bad' })), alerting(new FakeD1())));
await noAlert('method', () => call(req(undefined, { method: 'GET' }), alerting(new FakeD1())));
await noAlert('oversize', () => call(req(big), alerting(new FakeD1())));
await noAlert('content type', () => call(req(human(), { type: 'text/plain' }), alerting(new FakeD1())));
await noAlert('timing', () => call(req(human({ elapsedMs: 10 })), alerting(new FakeD1())));
await noAlert('throttle global', () => call(req(human()), alerting(new FakeD1().seed(20))));
await noAlert('throttle email', () => call(req(human()), alerting(new FakeD1().seed(3, { email: 'sam@example.com' }))));
await noAlert('no binding', () => call(req(human()), { RESEND_API_KEY: API_KEY, ALERT_TO }));
await noAlert('database error', () => call(req(human()), alerting(new FakeD1({ fail: true }))));

// The visitor's response must be byte-for-byte the same whatever happens to the alert.
const snapshot = r => ({ status: r.status, headers: r.headers, text: r.text, rejected: r.rejected });
out.baseline = snapshot(await call(req(human()), alerting(new FakeD1())));
out.variants = {};
async function variant(label, env, impl, opts) {
  const start = fetches.length;
  const previous = fetchImpl;
  if (impl) fetchImpl = impl;
  const r = await call(req(human()), env, opts);
  fetchImpl = previous;
  out.variants[label] = { ...snapshot(r), fetches: fetches.length - start };
}
const aborted = [];
await variant('no api key', { ENQUIRIES_DB: new FakeD1(), ALERT_TO });
await variant('empty api key', alerting(new FakeD1(), { RESEND_API_KEY: '' }));
await variant('no recipient', { ENQUIRIES_DB: new FakeD1(), RESEND_API_KEY: API_KEY });
await variant('resend 500', alerting(new FakeD1()), async () => new Response(RESEND_REPLY, { status: 500 }));
await variant('resend 422', alerting(new FakeD1()), async () => new Response(RESEND_REPLY, { status: 422 }));
await variant('fetch throws', alerting(new FakeD1()), async () => { throw new TypeError('network down ' + RESEND_REPLY); });
await variant('fetch rejects with abort', alerting(new FakeD1()), async () => { throw new DOMException('aborted', 'AbortError'); });
await variant('no waitUntil', alerting(new FakeD1()), null, { waitUntil: false });
// Hanging requests: shorten only the alert timer and record the delay the function asked for.
const realSetTimeout = globalThis.setTimeout;
const delays = [];
globalThis.setTimeout = (fn, ms, ...rest) => { delays.push(ms); return realSetTimeout(fn, Math.min(ms, 20), ...rest); };
await variant('hangs until aborted', alerting(new FakeD1()), (url, init) => new Promise((_, reject) => {
  init.signal.addEventListener('abort', () => { aborted.push(true); reject(new DOMException('aborted', 'AbortError')); });
}));
await variant('hangs and ignores abort', alerting(new FakeD1()), () => new Promise(() => {}));
globalThis.setTimeout = realSetTimeout;
out.alertDelays = delays;
out.aborted = aborted.length;
out.timeoutConstant = mod.ALERT_TIMEOUT_MS;
// waitUntil that throws must not change the response either.
{
  const start = fetches.length;
  const r = await mod.onRequest({ request: req(human()), env: alerting(new FakeD1()), waitUntil() { throw new Error('no ' + API_KEY); } });
  const text = await r.text();
  await new Promise(resolve => realSetTimeout(resolve, 10));
  out.variants['waitUntil throws'] = { status: r.status, headers: [...r.headers], text, rejected: 0, fetches: fetches.length - start };
}

// ---- Throttle ----
out.throttle = {};
async function throttleCase(label, db) {
  const before = db.rows.length;
  const r = await call(req(human()), alerting(db));
  out.throttle[label] = { status: r.status, body: r.body, retryAfter: r.retryAfter, cache: r.cache, added: db.rows.length - before, inserts: db.inserts() };
}
await throttleCase('global 20 in 10 min', new FakeD1().seed(20));
await throttleCase('global 25 in 10 min', new FakeD1().seed(25));
await throttleCase('global 19 in 10 min', new FakeD1().seed(19));
await throttleCase('global 25 older than 10 min', new FakeD1().seed(25, { ageMs: 11 * 60 * 1000 }));
await throttleCase('email 3 in an hour', new FakeD1().seed(3, { email: 'sam@example.com' }));
await throttleCase('email 2 in an hour', new FakeD1().seed(2, { email: 'sam@example.com' }));
await throttleCase('email 3 older than an hour', new FakeD1().seed(3, { email: 'sam@example.com', ageMs: 61 * 60 * 1000 }));
await throttleCase('other email 3 in an hour', new FakeD1().seed(3, { email: 'someone@example.com' }));

// A retry of an enquiry that was already stored is confirmed even when the throttle is full.
out.repeatWhenFull = {};
for (const [label, seedArgs] of [['global', [25]], ['email', [5, { email: 'sam@example.com' }]]]) {
  db = new FakeD1();
  await call(req(human()), alerting(db));
  db.seed(...seedArgs);
  const before = db.rows.length;
  const start = fetches.length;
  const r = await call(req(human()), alerting(db));
  out.repeatWhenFull[label] = { status: r.status, body: r.body, added: db.rows.length - before, fetches: fetches.length - start };
}
out.throttleConstants = mod.THROTTLE;

for (const level of Object.keys(realConsole)) console[level] = realConsole[level];
out.alertLogs = logs;
out.apiKey = API_KEY;
out.alertTo = ALERT_TO;
out.resendReply = RESEND_REPLY;

out.methods = {};
for (const method of ['GET', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']) {
  db = new FakeD1();
  const r = await call(req(undefined, { method }), { ENQUIRIES_DB: db });
  out.methods[method] = { status: r.status, allow: r.allow, calls: db.calls.length };
}
out.postAlias = mod.onRequestPost === mod.onRequest;
out.services = mod.SERVICES;
out.messages = mod.MESSAGES;
console.log(JSON.stringify(out));
""".replace('KEY_UPPER', json.dumps(KEY.upper()))

CLIENT_SCRIPT = r"""
const api = require(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const VALID = JSON.parse(process.argv[3]);
(async () => {
  const out = {};
  out.validation = cases.map(([label, overrides]) => {
    const r = api.validateEnquiry({ ...VALID, ...overrides });
    return { label, valid: r.valid, keys: Object.keys(r.errors).sort(), values: r.values, errors: r.errors };
  });
  out.services = api.SERVICES;
  out.messages = api.MESSAGES;
  const fake = (status, body, seen) => async (url, init) => {
    seen.push({ url, method: init.method, type: init.headers['Content-Type'], body: JSON.parse(init.body) });
    return { status, json: async () => { if (body === undefined) throw new SyntaxError('no json'); return body; } };
  };
  const seen = [];
  const payload = { ...VALID, elapsedMs: 5000 };
  out.r201 = await api.submitEnquiry(payload, fake(201, { ok: true, id: 7 }, seen));
  out.r200 = await api.submitEnquiry(payload, fake(200, { ok: true, id: 7 }, seen));
  out.r400 = await api.submitEnquiry(payload, fake(400, { ok: false, errors: { email: 'server text', bogus: 'x' } }, seen));
  out.r503 = await api.submitEnquiry(payload, fake(503, { ok: false, message: 'down' }, seen));
  out.r429 = await api.submitEnquiry(payload, fake(429, { ok: false, retry: true, message: 'wait' }, seen));
  out.r429html = await api.submitEnquiry(payload, fake(429, undefined, seen));
  out.r429okBody = await api.submitEnquiry(payload, fake(429, { ok: true }, seen));
  out.r500html = await api.submitEnquiry(payload, fake(500, undefined, seen));
  out.r200notOk = await api.submitEnquiry(payload, fake(200, { ok: false }, seen));
  out.rNetwork = await api.submitEnquiry(payload, async () => { throw new TypeError('Failed to fetch'); });
  out.request = seen[0];

  let n = 0;
  const keys = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-9222-222222222222', '33333333-3333-4333-a333-333333333333'];
  const sent = [];
  const plan = [503, 'network', 400, 201, 201];
  let step = 0;
  const flaky = async (url, init) => {
    const body = JSON.parse(init.body);
    sent.push({ key: body.idempotencyKey, elapsedMs: body.elapsedMs, company_url: body.company_url });
    const s = plan[step++];
    if (s === 'network') throw new TypeError('offline');
    return { status: s, json: async () => (s === 201 ? { ok: true, id: step } : s === 400 ? { ok: false, errors: { message: 'x' } } : { ok: false }) };
  };
  const sender = api.createSender(flaky, () => keys[n++]);
  const fields = { name: 'Sam', email: 'sam@example.com', service: 'not-sure', message: 'Hello there, website please.', company_url: '' };
  out.flow = [];
  for (let i = 0; i < plan.length; i++) out.flow.push((await sender.send(fields, 4000 + i)).kind);
  out.sentKeys = sent.map(s => s.key);
  out.sentElapsed = sent.map(s => s.elapsedMs);
  out.fieldsUntouched = !('idempotencyKey' in fields);

  // A 429 (timing check or rate limit) keeps the key; only the later success replaces it.
  let m = 0;
  const retrySent = [];
  const retryPlan = [429, 201, 201];
  let retryStep = 0;
  const limited = async (url, init) => {
    retrySent.push(JSON.parse(init.body).idempotencyKey);
    const s = retryPlan[retryStep++];
    return { status: s, json: async () => (s === 201 ? { ok: true, id: retryStep } : { ok: false, retry: true, message: 'wait' }) };
  };
  const retrySender = api.createSender(limited, () => keys[m++]);
  out.retryFlow = [];
  for (let i = 0; i < retryPlan.length; i++) out.retryFlow.push((await retrySender.send(fields, 500 + i * 1000)).kind);
  out.retrySentKeys = retrySent;

  out.outcomes = Object.fromEntries([
    ['success', { ok: true, kind: 'success', id: 1 }],
    ['invalid', { ok: false, kind: 'invalid', errors: { email: api.MESSAGES.email } }],
    ['invalidKey', { ok: false, kind: 'invalid', errors: { idempotencyKey: api.MESSAGES.idempotencyKey } }],
    ['unavailable', { ok: false, kind: 'unavailable' }],
    ['network', { ok: false, kind: 'network' }],
    ['retry', { ok: false, kind: 'retry' }],
    ['error', { ok: false, kind: 'error' }],
    ['garbage', { ok: false, kind: '__proto__' }],
    ['undefined', undefined],
  ].map(([k, v]) => [k, api.outcomeFor(v)]));
  out.notices = api.NOTICES;
  out.generatedKey = api.makeKey();
  console.log(JSON.stringify(out));
})();
"""


def node(*args):
    result = subprocess.run(['node', *args], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(f'node failed: {result.stderr}')
    return result


@functools.lru_cache(maxsize=None)
def server_results():
    with tempfile.TemporaryDirectory() as tmp:
        module = Path(tmp) / 'enquiry.mjs'
        shutil.copyfile(FUNCTION, module)
        script = Path(tmp) / 'run.mjs'
        script.write_text(SERVER_SCRIPT)
        return json.loads(node(str(script), module.as_uri(), json.dumps(CASES), json.dumps(VALID)).stdout)


class EnquiryFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = server_results()

    def test_valid_enquiry_is_created_with_normalised_values(self):
        self.assertEqual(self.r['created']['status'], 201)
        self.assertEqual(self.r['created']['body'], {'ok': True, 'id': 1})
        self.assertIn('application/json', self.r['created']['type'])
        self.assertEqual(self.r['created']['cache'], 'no-store')
        row = self.r['createdRows'][0]
        self.assertEqual(row['email'], 'sam@example.com')
        self.assertEqual(row['website'], 'https://example.com.au/')
        self.assertEqual(row['service'], 'website-redesign')
        self.assertEqual(row['idempotency_key'], KEY)
        self.assertRegex(row['created_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        self.assertNotIn('company_url', row)
        self.assertNotIn('elapsedMs', row)

    def test_each_invalid_field_is_rejected_with_its_key_and_no_write(self):
        expected = {label: sorted(keys) for label, _, keys in CASES if keys}
        self.assertEqual(set(self.r['invalid']), set(expected))
        for label, keys in expected.items():
            with self.subTest(label=label):
                result = self.r['invalid'][label]
                self.assertEqual(result['status'], 400)
                self.assertEqual(result['keys'], keys)
                self.assertEqual(result['calls'], 0)

    def test_repeated_key_returns_original_id_without_a_second_row(self):
        self.assertEqual(self.r['repeat']['status'], 200)
        self.assertEqual(self.r['repeat']['body'], {'ok': True, 'id': 1})
        self.assertEqual(self.r['repeatRows'], 1)
        self.assertEqual(self.r['newKey']['status'], 201)
        self.assertEqual(self.r['newKey']['body']['id'], 2)
        self.assertEqual(self.r['newKeyRows'], 2)
        # Keys are normalised to lower case, so an upper-case copy is still the same enquiry.
        self.assertEqual(self.r['upperKey']['status'], 200)
        self.assertEqual(self.r['upperKey']['body']['id'], 1)
        self.assertEqual(self.r['upperKeyRows'], 2)

    def test_sql_is_parameterised_and_contains_no_submitted_values(self):
        calls = self.r['allCalls']
        self.assertTrue(calls)
        submitted = [v for v in VALID.values() if isinstance(v, str)] + ['sam@example.com', 'https://example.com.au/', 'A second press']
        for call in calls:
            with self.subTest(sql=call['sql']):
                for value in submitted:
                    self.assertNotIn(value, call['sql'])
                self.assertEqual(call['sql'].count('?'), len(call['args']))
        # Order for a new enquiry: idempotency lookup, throttle counts, insert.
        sqls = [call['sql'] for call in self.r['createdCalls']]
        self.assertEqual(len(sqls), 3)
        self.assertTrue(sqls[0].startswith('SELECT id FROM enquiries WHERE idempotency_key'))
        self.assertIn('COUNT(*)', sqls[1])
        insert = sqls[2]
        self.assertIn('ON CONFLICT(idempotency_key) DO NOTHING', insert)
        self.assertIn('RETURNING id', insert)

    def test_oversize_bodies_are_rejected_on_actual_bytes(self):
        self.assertGreater(self.r['oversizeBytes'], 16 * 1024)
        self.assertEqual(self.r['oversize']['status'], 413)
        self.assertEqual(self.r['oversize']['calls'], 0)
        self.assertEqual(self.r['oversizeStream']['status'], 413)
        self.assertEqual(self.r['declaredOversize']['status'], 413)
        # Under 16 K characters but over 16 KB of UTF-8: the byte count decides.
        self.assertLess(self.r['multibyte']['chars'], 16 * 1024)
        self.assertGreater(self.r['multibyte']['bytes'], 16 * 1024)
        self.assertEqual(self.r['multibyte']['status'], 413)

    def test_content_type_and_body_shape(self):
        self.assertEqual(self.r['wrongType']['status'], 415)
        self.assertEqual(self.r['formType']['status'], 415)
        self.assertEqual(self.r['jsonCharset']['status'], 201)
        for key in ('badJson', 'arrayJson', 'badUtf8'):
            with self.subTest(case=key):
                self.assertEqual(self.r[key]['status'], 400)
                self.assertIs(self.r[key]['body']['ok'], False)

    def test_foreign_origin_is_forbidden(self):
        self.assertEqual(self.r['foreignOrigin']['status'], 403)
        self.assertEqual(self.r['nullOrigin']['status'], 403)
        self.assertEqual(self.r['sameOrigin']['status'], 201)

    def test_honeypot_gets_silent_success_and_no_database_call(self):
        self.assertEqual(len(self.r['bots']), 5)
        for label, result in self.r['bots'].items():
            with self.subTest(case=label):
                self.assertEqual(result['status'], 200)
                self.assertEqual(result['body'], {'ok': True})
                self.assertEqual(result['calls'], 0)
        self.assertEqual(self.r['blankHoneypot']['status'], 201)
        self.assertEqual(self.r['blankHoneypot']['calls'], 3)  # lookup, throttle, insert

    def test_fast_or_missing_timing_is_an_honest_retry_not_a_fake_success(self):
        self.assertEqual(len(self.r['tooFast']), 7)
        for label, result in self.r['tooFast'].items():
            with self.subTest(case=label):
                self.assertEqual(result['status'], 429)
                self.assertIs(result['body']['ok'], False)
                self.assertIs(result['body']['retry'], True)
                self.assertIn('not sent', result['body']['message'])
                self.assertNotIn('@', result['body']['message'])
                self.assertEqual(result['retryAfter'], '1')
                self.assertEqual(result['cache'], 'no-store')
                self.assertIn('application/json', result['type'])
                self.assertEqual(result['calls'], 0)

    def test_timing_at_or_above_800_ms_is_stored(self):
        for ms in ('800', '1200'):
            with self.subTest(ms=ms):
                self.assertEqual(self.r['humanTiming'][ms], {'status': 201, 'calls': 3})  # lookup, throttle, insert

    def test_spam_rejections_log_a_fixed_string_without_request_data(self):
        warnings = self.r['spamWarnings']
        self.assertEqual(warnings.count('enquiry: spam rejected (honeypot)'), 5)
        self.assertEqual(warnings.count('enquiry: spam rejected (timing)'), 7)
        self.assertEqual(len(warnings), 12)

    def test_missing_binding_is_503_and_names_no_email_address(self):
        for key in ('noBinding', 'noEnv'):
            with self.subTest(case=key):
                result = self.r[key]
                self.assertEqual(result['status'], 503)
                self.assertIs(result['body']['ok'], False)
                self.assertIn('nothing was sent', result['body']['message'])
                self.assertNotIn('@', result['body']['message'])
        self.assertEqual(self.r['invalidBeatsNoBinding']['status'], 400)

    def test_database_failure_is_503_without_internals(self):
        result = self.r['dbFail']
        self.assertEqual(result['status'], 503)
        self.assertEqual(result['calls'], 1)
        self.assertIs(result['body']['ok'], False)
        self.assertNotIn(self.r['secret'], result['text'])
        for fragment in ('D1_ERROR', 'enquiries_secret_internal', 'table', 'SQL', 'Error'):
            self.assertNotIn(fragment, result['text'])

    def test_budget_and_user_agent_are_not_collected(self):
        # Built scope: budget and user-agent data are not stored (docs/ENQUIRIES.md, "Differences from the task spec").
        result = self.r['budgetIgnored']
        self.assertEqual(result['status'], 201)
        insert = next(call['sql'] for call in result['calls'] if call['sql'].startswith('INSERT'))
        self.assertNotIn('budget', insert)
        self.assertNotIn('user_agent', insert)
        self.assertNotIn('A$5,000+', json.dumps(result['calls']))
        self.assertNotIn('budget', result['rows'][0])
        contact = (ROOT / 'pages' / 'contact.html').read_text()
        self.assertNotIn('name="budget"', contact)

    def test_only_post_is_allowed(self):
        self.assertTrue(self.r['postAlias'])
        for method, result in self.r['methods'].items():
            with self.subTest(method=method):
                self.assertEqual(result['status'], 405)
                self.assertEqual(result['allow'], 'POST')
                self.assertEqual(result['calls'], 0)

    def test_recorded_sql_runs_against_the_real_migration(self):
        db = sqlite3.connect(':memory:')
        db.executescript(MIGRATION.read_text())
        db.executescript(THROTTLE_MIGRATION.read_text())
        ids = []
        for call in self.r['allCalls']:
            row = db.execute(call['sql'], call['args']).fetchone()
            ids.append(row[0] if row else None)
        # lookup -> none; throttle counts -> 0 recent; insert -> id 1; repeat lookup -> id 1 (no second insert)
        self.assertEqual(ids, [None, 0, 1, 1])
        self.assertEqual(db.execute('SELECT COUNT(*) FROM enquiries').fetchone()[0], 1)
        self.assertEqual(db.execute('SELECT status, budget FROM enquiries').fetchone(), ('new', None))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE enquiries SET status = 'spam'")


RESEND_URL = 'https://api.resend.com/emails'


class EnquiryAlertTests(unittest.TestCase):
    """Task 30: one plain-text Resend alert per new enquiry, sent after the response and never affecting it."""

    @classmethod
    def setUpClass(cls):
        cls.r = server_results()

    def test_new_enquiry_sends_exactly_one_alert(self):
        self.assertEqual(self.r['fetchesWithoutSecrets'], 0)
        created = self.r['alertCreated']
        self.assertEqual(created['status'], 201)
        self.assertEqual(created['waited'], 1)
        self.assertEqual(created['rejected'], 0)
        fetches = self.r['alertFetches']
        self.assertEqual(len(fetches), 1)
        sent = fetches[0]
        self.assertEqual(sent['url'], RESEND_URL)
        self.assertEqual(sent['method'], 'POST')
        self.assertTrue(sent['signal'])
        self.assertEqual(sent['headers'], {'authorization': f"Bearer {self.r['apiKey']}", 'content-type': 'application/json'})
        body = sent['body']
        self.assertEqual(set(body), {'from', 'to', 'reply_to', 'subject', 'text'})
        self.assertNotIn('html', body)
        self.assertEqual(body['from'], 'Cendavo enquiries <onboarding@resend.dev>')
        self.assertEqual(body['to'], [self.r['alertTo']])
        self.assertEqual(body['reply_to'], 'sam@example.com')
        self.assertEqual(body['subject'], 'New enquiry: Sam Example (website-redesign)')
        text = body['text']
        for value in ('Sam Example', 'sam@example.com', '+61 (2) 5550-0000', 'Example Cleaning Co', 'https://example.com.au/',
                      'website-redesign', VALID['message'], 'Enquiry id: 1', 'typed by the visitor and is unverified'):
            with self.subTest(value=value):
                self.assertIn(value, text)
        self.assertRegex(text, r'Received \(UTC\): \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z')
        self.assertNotIn(KEY, text)
        self.assertNotIn(self.r['apiKey'], json.dumps(body))

    def test_reply_to_is_only_set_for_plain_addresses(self):
        results = self.r['replyTo']
        plain = results.pop('plain')
        self.assertEqual(plain['status'], 201)
        self.assertTrue(plain['hasReplyTo'])
        self.assertEqual(plain['replyTo'], 'jo.smith+quotes@example.com.au')
        self.assertEqual(len(results), 8)
        for label, result in results.items():
            with self.subTest(case=label):
                # The address is still valid for storage and still in the body, just never used as a header.
                self.assertEqual(result['status'], 201)
                self.assertEqual(result['fetches'], 1)
                self.assertFalse(result['hasReplyTo'])
                self.assertIn('Email: ', result['text'])
        self.assertIn('Email: <x@evil.com>', results['angle brackets']['text'])

    def test_no_alert_unless_a_new_row_was_inserted(self):
        expected = {'repeat': 200, 'honeypot': 200, 'invalid': 400, 'method': 405, 'oversize': 413, 'content type': 415,
                    'timing': 429, 'throttle global': 429, 'throttle email': 429, 'no binding': 503, 'database error': 503}
        self.assertEqual(set(self.r['noAlert']), set(expected))
        for label, status in expected.items():
            with self.subTest(case=label):
                self.assertEqual(self.r['noAlert'][label]['status'], status)
                self.assertEqual(self.r['noAlert'][label]['fetches'], 0)
                self.assertEqual(self.r['noAlert'][label]['waited'], 0)

    def test_response_is_identical_whatever_happens_to_the_alert(self):
        baseline = self.r['baseline']
        self.assertEqual(baseline['status'], 201)
        self.assertEqual(json.loads(baseline['text']), {'ok': True, 'id': 1})
        expected_fetches = {'no api key': 0, 'empty api key': 0, 'no recipient': 0, 'resend 500': 1, 'resend 422': 1,
                            'fetch throws': 1, 'fetch rejects with abort': 1, 'no waitUntil': 1, 'waitUntil throws': 1,
                            'hangs until aborted': 1, 'hangs and ignores abort': 1}
        self.assertEqual(set(self.r['variants']), set(expected_fetches))
        for label, count in expected_fetches.items():
            with self.subTest(case=label):
                result = dict(self.r['variants'][label])
                self.assertEqual(result.pop('fetches'), count)
                self.assertEqual(result, baseline)

    def test_hanging_alert_is_aborted_after_five_seconds(self):
        self.assertEqual(self.r['timeoutConstant'], 5000)
        self.assertEqual(self.r['alertDelays'], [5000, 5000])
        self.assertEqual(self.r['aborted'], 1)

    def test_alert_failures_log_one_fixed_string_without_secrets_or_visitor_data(self):
        logs = self.r['alertLogs']
        self.assertEqual(set(logs), {'enquiry: alert email failed', 'enquiry: throttled', 'enquiry: spam rejected (honeypot)',
                                     'enquiry: spam rejected (timing)', 'enquiry: database write failed Error'})
        # resend 500, resend 422, fetch throws, abort rejection, two hanging requests.
        self.assertEqual(logs.count('enquiry: alert email failed'), 6)
        joined = '\n'.join(logs)
        for secret in (self.r['apiKey'], self.r['alertTo'], self.r['resendReply'], 'invalid key', 'Sam Example', 'sam@example.com',
                       VALID['message'], 'network down'):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, joined)

    def test_source_calls_only_the_fixed_resend_url_and_keeps_the_key_server_side(self):
        source = FUNCTION.read_text()
        self.assertEqual(re.findall(r'\bfetch\(\s*([^,\s)]+)', source), ['RESEND_URL'])
        self.assertIn(f"const RESEND_URL = '{RESEND_URL}';", source)
        self.assertEqual(re.findall(r'https?://[^\s\'"`]+', source), [RESEND_URL])
        self.assertNotIn("'html'", source)
        self.assertNotIn('html:', source)
        self.assertIn('context.waitUntil(task)', source)
        for line in source.splitlines():
            if 'RESEND_API_KEY' in line and not line.strip().startswith('//'):
                with self.subTest(line=line.strip()):
                    self.assertNotIn('json(', line)
                    self.assertNotIn('console', line)
        # The browser script is unchanged in scope: same-origin only, nothing about alerts.
        client = CLIENT.read_text()
        for token in ('resend', 'RESEND', 'ALERT_TO'):
            self.assertNotIn(token, client)


class EnquiryThrottleTests(unittest.TestCase):
    """Task 30: 20 enquiries per 10 minutes overall and 3 per email address per hour, refused with the honest retry."""

    @classmethod
    def setUpClass(cls):
        cls.r = server_results()

    def test_limits(self):
        self.assertEqual(self.r['throttleConstants'], {'globalLimit': 20, 'globalWindowMs': 600000, 'emailLimit': 3, 'emailWindowMs': 3600000})

    def test_full_throttle_is_an_honest_retry_and_stores_nothing(self):
        retry_message = self.r['tooFast']['799 ms']['body']['message']
        for label in ('global 20 in 10 min', 'global 25 in 10 min', 'email 3 in an hour'):
            with self.subTest(case=label):
                result = self.r['throttle'][label]
                self.assertEqual(result['status'], 429)
                self.assertEqual(result['body'], {'ok': False, 'retry': True, 'message': retry_message})
                self.assertTrue(result['retryAfter'])
                self.assertEqual(result['cache'], 'no-store')
                self.assertEqual(result['added'], 0)
                self.assertEqual(result['inserts'], 0)

    def test_below_the_limits_or_outside_the_window_is_stored(self):
        for label in ('global 19 in 10 min', 'global 25 older than 10 min', 'email 2 in an hour', 'email 3 older than an hour',
                      'other email 3 in an hour'):
            with self.subTest(case=label):
                result = self.r['throttle'][label]
                self.assertEqual(result['status'], 201)
                self.assertEqual(result['added'], 1)

    def test_repeat_of_a_stored_enquiry_is_confirmed_even_when_throttled(self):
        for label in ('global', 'email'):
            with self.subTest(limit=label):
                result = self.r['repeatWhenFull'][label]
                self.assertEqual(result['status'], 200)
                self.assertEqual(result['body'], {'ok': True, 'id': 1})
                self.assertEqual(result['added'], 0)
                self.assertEqual(result['fetches'], 0)

    def test_throttle_queries_use_the_new_indexes(self):
        db = sqlite3.connect(':memory:')
        db.executescript(MIGRATION.read_text())
        db.executescript(THROTTLE_MIGRATION.read_text())
        throttle = next(call for call in self.r['allCalls'] if 'COUNT(*)' in call['sql'])
        self.assertEqual(len(throttle['args']), 3)
        self.assertEqual(throttle['args'][1], 'sam@example.com')
        for cutoff in (throttle['args'][0], throttle['args'][2]):
            self.assertRegex(cutoff, r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        plan = ' | '.join(row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + throttle['sql'], throttle['args']))
        self.assertIn('USING COVERING INDEX enquiries_created (created_at>?)', plan)
        self.assertIn('USING COVERING INDEX enquiries_email_created (email=? AND created_at>?)', plan)
        self.assertNotIn('SCAN enquiries', plan)


class MigrationTests(unittest.TestCase):
    def test_throttle_migration_adds_indexes_only_and_is_idempotent(self):
        sql = THROTTLE_MIGRATION.read_text()
        self.assertIn('CREATE INDEX IF NOT EXISTS enquiries_created ON enquiries (created_at);', sql)
        self.assertIn('CREATE INDEX IF NOT EXISTS enquiries_email_created ON enquiries (email, created_at);', sql)
        db = sqlite3.connect(':memory:')
        db.executescript(MIGRATION.read_text())
        before = [row[1] for row in db.execute('PRAGMA table_info(enquiries)')]
        db.executescript(sql)
        db.executescript(sql)  # idempotent re-run
        after = [row[1] for row in db.execute('PRAGMA table_info(enquiries)')]
        self.assertEqual(before, after)
        for column in after:
            self.assertNotRegex(column, r'ip|user_agent|agent')
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(indexes, {'enquiries_status_created', 'enquiries_created', 'enquiries_email_created'})

    def test_schema_constraints_and_no_tracking_columns(self):
        sql = MIGRATION.read_text()
        self.assertRegex(sql, r'idempotency_key TEXT NOT NULL UNIQUE')
        self.assertRegex(sql, r"CHECK \(status IN \('new', 'contacted', 'qualified', 'closed'\)\)")
        self.assertRegex(sql, r"status TEXT NOT NULL DEFAULT 'new'")
        db = sqlite3.connect(':memory:')
        db.executescript(sql)
        db.executescript(sql)  # idempotent re-run
        columns = [row[1] for row in db.execute('PRAGMA table_info(enquiries)')]
        self.assertEqual(columns, ['id', 'created_at', 'name', 'email', 'phone', 'business', 'website', 'service', 'budget', 'message', 'status', 'idempotency_key'])
        for column in columns:
            self.assertNotRegex(column, r'ip|user_agent|agent')


class EnquiryClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = node('-e', CLIENT_SCRIPT, str(CLIENT), json.dumps(CASES), json.dumps(VALID))
        cls.r = json.loads(out.stdout)
        cls.server = server_results()

    def test_client_script_syntax(self):
        result = node('--check', str(CLIENT))
        self.assertEqual(result.returncode, 0)

    def test_shared_table_matches_expected_on_client_and_server(self):
        for side, results in (('client', self.r['validation']), ('server', self.server['validation'])):
            for (label, _, keys), result in zip(CASES, results):
                with self.subTest(side=side, case=label):
                    self.assertEqual(result['label'], label)
                    self.assertEqual(result['keys'], sorted(keys))
                    self.assertEqual(result['valid'], not keys)

    def test_client_and_server_agree_exactly(self):
        self.assertEqual(self.r['validation'], self.server['validation'])
        self.assertEqual(self.r['services'], self.server['services'])
        self.assertEqual(self.r['messages'], self.server['messages'])

    def test_submit_maps_responses(self):
        self.assertEqual(self.r['request'], {'url': '/api/enquiry', 'method': 'POST', 'type': 'application/json',
                                             'body': {**VALID, 'elapsedMs': 5000}})
        self.assertEqual(self.r['r201'], {'ok': True, 'kind': 'success', 'id': 7})
        self.assertEqual(self.r['r200'], {'ok': True, 'kind': 'success', 'id': 7})
        # Server field errors are shown with the client's own message, unknown fields are dropped.
        self.assertEqual(self.r['r400'], {'ok': False, 'kind': 'invalid', 'errors': {'email': self.r['messages']['email']}})
        self.assertEqual(self.r['r503'], {'ok': False, 'kind': 'unavailable'})
        # 429 means "nothing stored, try again", whatever the body says (Cloudflare rate limits send HTML).
        for key in ('r429', 'r429html', 'r429okBody'):
            with self.subTest(case=key):
                self.assertEqual(self.r[key], {'ok': False, 'kind': 'retry'})
        self.assertEqual(self.r['r500html'], {'ok': False, 'kind': 'error'})
        self.assertEqual(self.r['r200notOk'], {'ok': False, 'kind': 'error'})
        self.assertEqual(self.r['rNetwork'], {'ok': False, 'kind': 'network'})

    def test_key_is_reused_after_failure_and_replaced_after_success(self):
        self.assertEqual(self.r['flow'], ['unavailable', 'network', 'invalid', 'success', 'success'])
        k1, k2, k3 = ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-9222-222222222222',
                      '33333333-3333-4333-a333-333333333333')
        self.assertEqual(self.r['sentKeys'], [k1, k1, k1, k1, k2])
        self.assertEqual(self.r['sentElapsed'], [4000, 4001, 4002, 4003, 4004])
        self.assertTrue(self.r['fieldsUntouched'])
        self.assertRegex(self.r['generatedKey'], r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
        self.assertNotIn(k3, self.r['sentKeys'])

    def test_retry_after_429_reuses_the_key_until_success(self):
        k1, k2 = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-9222-222222222222'
        self.assertEqual(self.r['retryFlow'], ['retry', 'success', 'success'])
        self.assertEqual(self.r['retrySentKeys'], [k1, k1, k2])

    def test_only_success_clears_the_form(self):
        outcomes = self.r['outcomes']
        self.assertTrue(outcomes['success']['reset'])
        self.assertEqual(outcomes['success']['tone'], 'success')
        for kind in ('invalid', 'invalidKey', 'unavailable', 'network', 'retry', 'error', 'garbage', 'undefined'):
            with self.subTest(kind=kind):
                self.assertFalse(outcomes[kind]['reset'])
                self.assertEqual(outcomes[kind]['tone'], 'error')
        self.assertEqual(outcomes['invalid']['errors'], {'email': self.r['messages']['email']})
        self.assertEqual(outcomes['garbage']['message'], self.r['notices']['error'])
        self.assertEqual(outcomes['invalidKey']['message'], self.r['messages']['idempotencyKey'])
        for kind in ('unavailable', 'network', 'retry', 'error'):
            self.assertIn('Your details are still in the form', outcomes[kind]['message'])
            self.assertNotIn('@', outcomes[kind]['message'])
        self.assertEqual(outcomes['retry']['message'], self.r['notices']['retry'])
        self.assertEqual(outcomes['retry']['errors'], {})
        self.assertIn('not sent', self.r['notices']['retry'])
        self.assertIn('wait a moment', self.r['notices']['retry'])
        self.assertIn('send again', self.r['notices']['retry'])

    def test_client_source_is_safe(self):
        source = CLIENT.read_text()
        self.assertNotIn('innerHTML', source)
        self.assertNotIn('insertAdjacentHTML', source)
        self.assertNotIn('eval(', source)
        self.assertEqual(source.count('form.reset()'), 1)
        # Same-origin relative endpoint only; no third-party requests.
        self.assertIn("doFetch('/api/enquiry'", source)
        self.assertNotRegex(source, r"[Ff]etch\(\s*['\"]https?:")
        self.assertIn('first.focus()', source)
        self.assertIn('button.disabled = true', source)
        # Elapsed time uses the monotonic clock where available.
        self.assertIn('performance.now()', source)
        self.assertNotIn('Date.now() - startedAt', source)


if __name__ == '__main__':
    unittest.main()
