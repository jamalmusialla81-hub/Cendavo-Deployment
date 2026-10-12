// Contact page enquiry form. Loaded only on /contact/. The validation rules and messages mirror
// functions/api/enquiry.js; tests/test_enquiry.py checks both against one shared case table.
(function () {
  'use strict';

  var SERVICES = ['website-design', 'website-redesign', 'maintenance', 'not-sure'];
  var FIELDS = ['name', 'email', 'phone', 'business', 'website', 'service', 'message'];
  var MESSAGES = {
    name: 'Enter your name (up to 100 characters).',
    email: 'Enter a valid email address, like name@example.com.',
    phone: 'Enter a phone number using digits, spaces and + ( ) - only (up to 30 characters).',
    business: 'Keep the business name to 120 characters or fewer.',
    website: 'Enter a website address, like example.com.au (up to 200 characters).',
    service: 'Choose the service you are interested in.',
    message: 'Tell us a little about your project (10 to 2000 characters).',
    idempotencyKey: 'Please reload the page and try again.'
  };
  // The public business address, the fallback when sending fails. Must match CONTACT_EMAIL in scripts/build_site.py and
  // functions/api/enquiry.js. Notices are plain text (written with textContent), so the address is not a link here.
  var CONTACT_EMAIL = 'cendavo.au@gmail.com';
  var NOTICES = {
    success: 'Thank you. Your enquiry has been received and we will reply to the email address you gave.',
    invalid: 'Please check the highlighted fields.',
    retry: 'Your enquiry was not sent. Your details are still in the form. Please wait a moment and press send again.',
    unavailable: 'Enquiries are temporarily unavailable, so nothing was sent. Your details are still in the form. Please try again later or email ' + CONTACT_EMAIL + '.',
    network: 'We could not reach the server, so your enquiry may not have been sent. Your details are still in the form. Check your connection and try again, or email ' + CONTACT_EMAIL + '.',
    error: 'Your enquiry could not be sent. Your details are still in the form. Please try again later or email ' + CONTACT_EMAIL + '.'
  };
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var PHONE = /^[0-9+() -]+$/;
  var UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  var TIMEOUT_MS = 15000;

  function clean(value, multiline) {
    if (value === undefined || value === null) return '';
    if (typeof value !== 'string') return null;
    if (multiline) {
      return value.replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').trim();
    }
    return value.replace(/[\s\u0000-\u001f\u007f]+/g, ' ').trim();
  }

  function normaliseWebsite(value) {
    var candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : 'https://' + value;
    var url;
    try {
      url = new URL(candidate);
    } catch (e) {
      return null;
    }
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || url.username || url.password || url.hostname.indexOf('.') === -1) return null;
    return url.href.length <= 200 ? url.href : null;
  }

  function validateEnquiry(input) {
    var source = input && typeof input === 'object' && !Array.isArray(input) ? input : {};
    var errors = {};
    var values = {};

    var name = clean(source.name);
    if (!name || name.length > 100) errors.name = MESSAGES.name;
    else values.name = name;

    var email = clean(source.email);
    if (!email || email.length > 254 || !EMAIL.test(email)) errors.email = MESSAGES.email;
    else values.email = email.toLowerCase();

    var phone = clean(source.phone);
    if (phone === null || (phone && (phone.length > 30 || !PHONE.test(phone) || !/[0-9]/.test(phone)))) errors.phone = MESSAGES.phone;
    else values.phone = phone || null;

    var business = clean(source.business);
    if (business === null || business.length > 120) errors.business = MESSAGES.business;
    else values.business = business || null;

    var website = clean(source.website);
    if (website === null || website.length > 200) errors.website = MESSAGES.website;
    else if (website) {
      var href = normaliseWebsite(website);
      if (href) values.website = href;
      else errors.website = MESSAGES.website;
    } else values.website = null;

    var service = clean(source.service);
    if (SERVICES.indexOf(service) === -1) errors.service = MESSAGES.service;
    else values.service = service;

    var message = clean(source.message, true);
    if (!message || message.length < 10 || message.length > 2000) errors.message = MESSAGES.message;
    else values.message = message;

    var key = clean(source.idempotencyKey);
    if (!key || !UUID_V4.test(key.toLowerCase())) errors.idempotencyKey = MESSAGES.idempotencyKey;
    else values.idempotencyKey = key.toLowerCase();

    return { valid: Object.keys(errors).length === 0, values: values, errors: errors };
  }

  function makeKey() {
    var c = typeof crypto !== 'undefined' ? crypto : null;
    if (c && typeof c.randomUUID === 'function') return c.randomUUID();
    var b = new Uint8Array(16);
    c.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return (x + 256).toString(16).slice(1); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }

  // Sends one enquiry. Resolves (never rejects) to {ok, kind, id?, errors?}.
  async function submitEnquiry(payload, fetchImpl) {
    var doFetch = fetchImpl || (typeof fetch === 'function' ? fetch : null);
    if (!doFetch) return { ok: false, kind: 'network' };
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;
    var response;
    try {
      response = await doFetch('/api/enquiry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'same-origin',
        signal: controller ? controller.signal : undefined
      });
    } catch (e) {
      return { ok: false, kind: 'network' };
    } finally {
      if (timer) clearTimeout(timer);
    }
    var data = null;
    try {
      data = await response.json();
    } catch (e) {
      data = null;
    }
    if ((response.status === 200 || response.status === 201) && data && data.ok === true) {
      return { ok: true, kind: 'success', id: typeof data.id === 'number' ? data.id : null };
    }
    if (response.status === 400 && data && data.errors && typeof data.errors === 'object') {
      var errors = {};
      Object.keys(MESSAGES).forEach(function (field) {
        if (Object.prototype.hasOwnProperty.call(data.errors, field)) errors[field] = MESSAGES[field];
      });
      return { ok: false, kind: 'invalid', errors: errors };
    }
    // 429: the server's timing check or a Cloudflare rate limit. Nothing was stored; ask for a retry.
    if (response.status === 429) return { ok: false, kind: 'retry' };
    if (response.status === 503) return { ok: false, kind: 'unavailable' };
    return { ok: false, kind: 'error' };
  }

  // Holds one idempotency key per enquiry: reused for every retry, replaced only after success.
  function createSender(fetchImpl, keyFactory) {
    var newKey = keyFactory || makeKey;
    var key = newKey();
    return {
      key: function () { return key; },
      send: async function (fields, elapsedMs) {
        var payload = {};
        Object.keys(fields || {}).forEach(function (k) { payload[k] = fields[k]; });
        payload.idempotencyKey = key;
        payload.elapsedMs = elapsedMs;
        var result = await submitEnquiry(payload, fetchImpl);
        if (result.ok) key = newKey();
        return result;
      }
    };
  }

  // What the page should do with a result. Only success clears the form.
  function outcomeFor(result) {
    if (result && result.ok) return { reset: true, tone: 'success', message: NOTICES.success, errors: {} };
    var known = result && typeof result.kind === 'string' && result.kind !== 'success' && Object.prototype.hasOwnProperty.call(NOTICES, result.kind);
    var kind = known ? result.kind : 'error';
    var errors = kind === 'invalid' && result.errors ? result.errors : {};
    var message = NOTICES[kind];
    if (kind === 'invalid' && errors.idempotencyKey) message = MESSAGES.idempotencyKey;
    return { reset: false, tone: 'error', message: message, errors: errors };
  }

  var api = { CONTACT_EMAIL: CONTACT_EMAIL, SERVICES: SERVICES, MESSAGES: MESSAGES, NOTICES: NOTICES, validateEnquiry: validateEnquiry, submitEnquiry: submitEnquiry, createSender: createSender, outcomeFor: outcomeFor, makeKey: makeKey };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document === 'undefined') return;

  var form = document.querySelector('[data-enquiry]');
  if (!form) return;
  var status = document.querySelector('[data-enquiry-status]');
  var button = form.querySelector('[type="submit"]');
  var idleLabel = button ? button.textContent : '';
  // Monotonic clock where available, so a system clock change cannot make elapsed time negative.
  var now = typeof performance !== 'undefined' && performance && typeof performance.now === 'function'
    ? function () { return performance.now(); }
    : function () { return Date.now(); };
  var startedAt = now();
  var sender = createSender();
  var sending = false;

  function announce(message, tone) {
    if (!status) return;
    status.textContent = '';
    status.setAttribute('data-tone', tone);
    requestAnimationFrame(function () { status.textContent = message; });
  }

  function showErrors(errors) {
    var first = null;
    FIELDS.forEach(function (field) {
      var control = form.elements[field];
      var slot = form.querySelector('[data-error-for="' + field + '"]');
      var message = errors[field] || '';
      if (slot) slot.textContent = message;
      if (!control) return;
      if (message) {
        control.setAttribute('aria-invalid', 'true');
        if (!first) first = control;
      } else {
        control.removeAttribute('aria-invalid');
      }
    });
    if (first) first.focus();
    return first;
  }

  function readFields() {
    var fields = {};
    FIELDS.concat('company_url').forEach(function (field) {
      var control = form.elements[field];
      fields[field] = control ? control.value : '';
    });
    return fields;
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (sending) return;
    var fields = readFields();
    var check = validateEnquiry(Object.assign({}, fields, { idempotencyKey: sender.key() }));
    if (!check.valid) {
      showErrors(check.errors);
      announce(check.errors.idempotencyKey && Object.keys(check.errors).length === 1 ? MESSAGES.idempotencyKey : NOTICES.invalid, 'error');
      return;
    }
    showErrors({});
    sending = true;
    form.setAttribute('aria-busy', 'true');
    if (button) {
      button.disabled = true;
      button.textContent = 'Sending…';
    }
    announce('Sending your enquiry…', 'info');
    var result = await sender.send(fields, Math.round(now() - startedAt));
    var outcome = outcomeFor(result);
    sending = false;
    form.removeAttribute('aria-busy');
    if (button) {
      button.disabled = false;
      button.textContent = idleLabel;
    }
    if (outcome.reset) {
      form.reset();
      startedAt = now();
    } else {
      showErrors(outcome.errors);
    }
    announce(outcome.message, outcome.tone);
  });
})();
