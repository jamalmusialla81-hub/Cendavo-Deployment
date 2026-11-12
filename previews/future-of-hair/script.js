/* Cendavo barber preview — shared behaviour. No network requests. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* Hero entrance */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { root.classList.add("loaded"); });
    });

    /* Scroll reveals */
    var rvs = document.querySelectorAll(".rv");
    if (reduce || !("IntersectionObserver" in window)) {
      rvs.forEach(function (el) { el.classList.add("in"); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
      rvs.forEach(function (el) { io.observe(el); });
    }

    /* Day chips: next N days, generated in the visitor's locale (en-AU) */
    document.querySelectorAll("[data-days]").forEach(function (box) {
      var n = parseInt(box.getAttribute("data-days"), 10) || 7;
      var name = box.getAttribute("data-name") || "day";
      var req = box.hasAttribute("data-required");
      var now = new Date();
      var html = "";
      for (var i = 0; i < n; i++) {
        var d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
        var wk = d.toLocaleDateString("en-AU", { weekday: "short" });
        var label = i === 0 ? "Today" : i === 1 ? "Tomorrow" : wk;
        var long = d.toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long" });
        var val = (i === 0 ? "Today, " : i === 1 ? "Tomorrow, " : "") + long;
        html += '<label class="chip"><input type="radio" name="' + name + '" value="' + val + '"' +
          (req && i === 0 ? " required" : "") + '><span><small>' + label + "</small><b>" + d.getDate() +
          "</b><small>" + d.toLocaleDateString("en-AU", { month: "short" }) + "</small></span></label>";
      }
      box.innerHTML = html;
    });

    /* Live summaries */
    function updateSummary(form) {
      (form.closest("section") || form).querySelectorAll("[data-sum]").forEach(function (out) {
        var key = out.getAttribute("data-sum");
        var picked = form.querySelector('[name="' + key + '"]:checked');
        var field = picked || form.querySelector('[name="' + key + '"]:not([type="radio"])');
        var v = field && field.value ? field.value : "";
        var empty = out.getAttribute("data-empty") || "";
        out.textContent = v || empty;
        out.classList.toggle("is-set", !!v);
      });
    }

    /* File input labels */
    document.querySelectorAll(".file input[type=file]").forEach(function (inp) {
      inp.addEventListener("change", function () {
        var t = inp.closest(".file").querySelector("[data-file-name]");
        if (t) t.textContent = inp.files && inp.files.length ? inp.files[0].name + " — attached (preview only)" : t.getAttribute("data-default");
      });
    });

    document.querySelectorAll("form.booking").forEach(function (form) {
      form.setAttribute("novalidate", "");
      form.addEventListener("change", function () { updateSummary(form); });
      form.addEventListener("input", function () { updateSummary(form); });
      updateSummary(form);

      var msg = form.querySelector(".preview-msg");

      /* Optional stepper */
      var steps = Array.prototype.slice.call(form.querySelectorAll(".step"));
      var stepper = form.hasAttribute("data-stepper") && steps.length > 1;
      var cur = 0;
      var bar = form.querySelector(".progress span");
      var count = form.querySelector("[data-count]");
      var navItems = form.querySelectorAll(".steps-nav li");
      var err = form.querySelector(".step-error");

      function validIn(scope) {
        var fields = scope.querySelectorAll("input, select, textarea");
        for (var i = 0; i < fields.length; i++) {
          var f = fields[i];
          if (f.type === "radio") {
            if (f.required && !form.querySelector('[name="' + f.name + '"]:checked')) return f;
          } else if (!f.checkValidity()) return f;
        }
        return null;
      }

      function show(i, focus) {
        cur = Math.max(0, Math.min(steps.length - 1, i));
        steps.forEach(function (s, k) { s.classList.toggle("on", k === cur); });
        navItems.forEach(function (li, k) {
          li.classList.toggle("on", k === cur);
          li.classList.toggle("done", k < cur);
        });
        if (bar) bar.style.width = ((cur + 1) / steps.length) * 100 + "%";
        if (count) count.textContent = "Step " + (cur + 1) + " of " + steps.length;
        if (err) err.textContent = "";
        var nb = form.querySelector("[data-next]");
        var bb = form.querySelector("[data-back]");
        if (nb) nb.innerHTML = cur === steps.length - 1 ? 'Request booking <span class="arr" aria-hidden="true">\u2192</span>' : 'Next <span class="arr" aria-hidden="true">\u2192</span>';
        if (bb) bb.disabled = cur === 0;
        if (focus) {
          var lg = steps[cur].querySelector(".legend");
          if (lg) { lg.setAttribute("tabindex", "-1"); lg.focus({ preventScroll: true }); }
        }
      }

      if (stepper) {
        show(0, false);
        form.addEventListener("click", function (e) {
          var nx = e.target.closest("[data-next]");
          var bk = e.target.closest("[data-back]");
          if (nx) {
            e.preventDefault();
            var bad = validIn(steps[cur]);
            if (bad) {
              if (err) err.textContent = bad.type === "radio" ? "Pick one to continue." : (bad.validationMessage || "Please check this field.");
              if (bad.type !== "radio") bad.focus();
              return;
            }
            if (cur === steps.length - 1) {
              if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event("submit", { cancelable: true }));
            } else show(cur + 1, true);
          }
          if (bk) { e.preventDefault(); show(cur - 1, true); }
        });
        /* Auto-advance on single-choice steps for speed */
        steps.forEach(function (s, k) {
          if (!s.hasAttribute("data-auto")) return;
          s.addEventListener("change", function (e) {
            if (e.target.type === "radio" && k === cur && k < steps.length - 1) {
              setTimeout(function () { show(k + 1, true); }, reduce ? 0 : 260);
            }
          });
        });
      }

      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var bad = validIn(form);
        if (bad) {
          if (stepper) {
            var idx = steps.indexOf(bad.closest(".step"));
            if (idx > -1) show(idx, false);
          }
          if (err) err.textContent = bad.type === "radio" ? "Pick one to continue." : (bad.validationMessage || "Please check this field.");
          if (bad.type === "radio") {
            var group = bad.closest("fieldset");
            if (group) group.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
            bad.focus();
          } else {
            bad.reportValidity ? bad.reportValidity() : bad.focus();
          }
          return;
        }
        if (msg) {
          msg.hidden = false;
          msg.setAttribute("tabindex", "-1");
          msg.focus({ preventScroll: true });
          msg.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
        }
      });
    });
  });
})();

/* Multi-page shell: mobile menu, cut picker tabs, link-in-bio sheet, booking prefill */
(function () {
  "use strict";
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  ready(function () {
    var root = document.documentElement;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* Mobile menu */
    var btn = document.querySelector(".menu-btn");
    var panel = document.getElementById("menu");
    var header = document.querySelector(".site-header");
    function setHdr() {
      if (header) root.style.setProperty("--hdr", Math.round(header.getBoundingClientRect().bottom) + "px");
    }
    function closeMenu(focusBtn) {
      if (!panel || !panel.classList.contains("open")) return;
      panel.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
      btn.querySelector(".lbl").textContent = "Menu";
      document.body.classList.remove("menu-open");
      if (focusBtn) btn.focus();
    }
    if (btn && panel) {
      btn.addEventListener("click", function () {
        if (panel.classList.contains("open")) { closeMenu(false); return; }
        setHdr();
        panel.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
        btn.querySelector(".lbl").textContent = "Close";
        document.body.classList.add("menu-open");
        var first = panel.querySelector("a");
        if (first) first.focus({ preventScroll: true });
      });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenu(true); });
      panel.addEventListener("click", function (e) { if (e.target.closest("a")) closeMenu(false); });
      window.addEventListener("resize", function () { if (window.innerWidth >= 900) closeMenu(false); });
    }

    /* Tabs (cut picker) */
    document.querySelectorAll("[data-tabs]").forEach(function (box) {
      var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
      function select(t, focus) {
        tabs.forEach(function (x) {
          var on = x === t;
          x.setAttribute("aria-selected", on ? "true" : "false");
          x.tabIndex = on ? 0 : -1;
          var p = document.getElementById(x.getAttribute("aria-controls"));
          if (p) p.hidden = !on;
        });
        if (focus) t.focus();
      }
      tabs.forEach(function (t, i) {
        t.addEventListener("click", function () { select(t, false); });
        t.addEventListener("keydown", function (e) {
          var k = e.key, n = null;
          if (k === "ArrowRight" || k === "ArrowDown") n = tabs[(i + 1) % tabs.length];
          if (k === "ArrowLeft" || k === "ArrowUp") n = tabs[(i - 1 + tabs.length) % tabs.length];
          if (k === "Home") n = tabs[0];
          if (k === "End") n = tabs[tabs.length - 1];
          if (n) { e.preventDefault(); select(n, true); }
        });
      });
      if (tabs.length) select(tabs[0], false);
    });

    /* Link-in-bio sheet */
    document.querySelectorAll("[data-sheet-open]").forEach(function (opener) {
      var sheet = document.getElementById(opener.getAttribute("aria-controls"));
      var scrim = sheet && sheet.parentNode.querySelector(".sheet-scrim");
      if (!sheet) return;
      sheet.setAttribute("aria-hidden", "true");
      sheet.querySelectorAll("a, button").forEach(function (el) { el.tabIndex = -1; });
      function set(open) {
        sheet.classList.toggle("open", open);
        if (scrim) scrim.classList.toggle("on", open);
        opener.setAttribute("aria-expanded", open ? "true" : "false");
        sheet.setAttribute("aria-hidden", open ? "false" : "true");
        sheet.querySelectorAll("a, button").forEach(function (el) { el.tabIndex = open ? 0 : -1; });
        if (open) { var f = sheet.querySelector("a"); if (f) setTimeout(function () { f.focus({ preventScroll: true }); }, reduce ? 0 : 300); }
        else opener.focus({ preventScroll: true });
      }
      opener.addEventListener("click", function () { set(!sheet.classList.contains("open")); });
      sheet.querySelectorAll("[data-sheet-close]").forEach(function (c) { c.addEventListener("click", function () { set(false); }); });
      if (scrim) scrim.addEventListener("click", function () { set(false); });
      sheet.addEventListener("keydown", function (e) { if (e.key === "Escape") set(false); });
    });

    /* Prefill booking service from ?service= (links from Cuts / Home) */
    var svc = null;
    try { svc = new URLSearchParams(window.location.search).get("service"); } catch (e) { svc = null; }
    if (svc) {
      document.querySelectorAll("form.booking").forEach(function (form) {
        var match = null;
        form.querySelectorAll('input[name="service"]').forEach(function (r) { if (r.value === svc) match = r; });
        if (match) {
          match.checked = true;
          match.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    }
  });
})();
