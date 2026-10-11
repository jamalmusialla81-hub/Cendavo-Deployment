"""Enquiry workflow: Pages Function, D1 schema, browser script and contact page.

The function is an ES module, so it is copied into a temporary directory as .mjs and imported with Node;
the browser script is a classic script loaded with require(). Both run the same validation case table.
"""
import functools
import json
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
    throw new Error('unexpected SQL ' + sql);
  }
}

const URL_ = 'https://cendavo.example/api/enquiry';
function req(body, { method = 'POST', type = 'application/json', headers = {} } = {}) {
  const init = { method, headers: { ...(type ? { 'content-type': type } : {}), ...headers } };
  if (body !== undefined && method !== 'GET' && method !== 'HEAD') init.body = typeof body === 'string' ? body : JSON.stringify(body);
  return new Request(URL_, init);
}
const human = extra => ({ ...VALID, elapsedMs: 8000, ...extra });
async function call(request, env) {
  const res = await mod.onRequest({ request, env });
  const text = await res.text();
  let body = null; try { body = JSON.parse(text); } catch {}
  return { status: res.status, body, text, allow: res.headers.get('allow'), type: res.headers.get('content-type'), cache: res.headers.get('cache-control') };
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

out.bots = {};
for (const [label, extra] of [
  ['honeypot', { company_url: 'https://spam.example' }],
  ['honeypot non-string', { company_url: 1 }],
  ['too fast', { elapsedMs: 1200 }],
  ['no timing', { elapsedMs: undefined }],
  ['timing as string', { elapsedMs: '9000' }],
  ['honeypot with invalid fields', { company_url: 'x', email: 'bad' }],
]) {
  db = new FakeD1();
  const r = await call(req(human(extra)), { ENQUIRIES_DB: db });
  out.bots[label] = { status: r.status, body: r.body, calls: db.calls.length };
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

  out.outcomes = Object.fromEntries([
    ['success', { ok: true, kind: 'success', id: 1 }],
    ['invalid', { ok: false, kind: 'invalid', errors: { email: api.MESSAGES.email } }],
    ['invalidKey', { ok: false, kind: 'invalid', errors: { idempotencyKey: api.MESSAGES.idempotencyKey } }],
    ['unavailable', { ok: false, kind: 'unavailable' }],
    ['network', { ok: false, kind: 'network' }],
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
        insert = self.r['createdCalls'][0]['sql']
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

    def test_spam_gets_fake_success_and_no_database_call(self):
        for label, result in self.r['bots'].items():
            with self.subTest(case=label):
                self.assertEqual(result['status'], 200)
                self.assertEqual(result['body'], {'ok': True})
                self.assertEqual(result['calls'], 0)
        self.assertEqual(self.r['blankHoneypot']['status'], 201)
        self.assertEqual(self.r['blankHoneypot']['calls'], 1)

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
        self.assertNotIn('budget', result['calls'][0]['sql'])
        self.assertNotIn('user_agent', result['calls'][0]['sql'])
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
        ids = []
        for call in self.r['allCalls']:
            row = db.execute(call['sql'], call['args']).fetchone()
            ids.append(row[0] if row else None)
        # insert -> id 1; repeat insert -> no row; lookup -> id 1
        self.assertEqual(ids, [1, None, 1])
        self.assertEqual(db.execute('SELECT COUNT(*) FROM enquiries').fetchone()[0], 1)
        self.assertEqual(db.execute('SELECT status, budget FROM enquiries').fetchone(), ('new', None))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE enquiries SET status = 'spam'")


class MigrationTests(unittest.TestCase):
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

    def test_only_success_clears_the_form(self):
        outcomes = self.r['outcomes']
        self.assertTrue(outcomes['success']['reset'])
        self.assertEqual(outcomes['success']['tone'], 'success')
        for kind in ('invalid', 'invalidKey', 'unavailable', 'network', 'error', 'garbage', 'undefined'):
            with self.subTest(kind=kind):
                self.assertFalse(outcomes[kind]['reset'])
                self.assertEqual(outcomes[kind]['tone'], 'error')
        self.assertEqual(outcomes['invalid']['errors'], {'email': self.r['messages']['email']})
        self.assertEqual(outcomes['garbage']['message'], self.r['notices']['error'])
        self.assertEqual(outcomes['invalidKey']['message'], self.r['messages']['idempotencyKey'])
        for kind in ('unavailable', 'network', 'error'):
            self.assertIn('Your details are still in the form', outcomes[kind]['message'])
            self.assertNotIn('@', outcomes[kind]['message'])

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


if __name__ == '__main__':
    unittest.main()
