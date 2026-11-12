/* Cendavo concept preview — interactions (no network requests, no libraries) */
(function () {
  "use strict";
  var doc = document.documentElement;
  doc.classList.remove("no-js");
  doc.classList.add("js");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) doc.classList.add("reduced");

  // Hero entrance
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { document.body.classList.add("is-ready"); });
  });

  // Header shadow + action bar reveal
  var header = document.querySelector(".site-header");
  var bar = document.querySelector(".action-bar");
  function onScroll() {
    var y = window.scrollY || window.pageYOffset;
    if (header) header.classList.toggle("is-scrolled", y > 8);
    if (bar) bar.classList.toggle("is-visible", y > 220 || window.innerWidth < 900);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Measuring tape drifts gently with scroll
  var tracks = document.querySelectorAll(".tape-track");
  if (tracks.length && !reduced) {
    var ticking = false;
    var moveTape = function () {
      var off = ((window.scrollY || 0) * 0.18) % 1000;
      tracks.forEach(function (t, i) {
        t.style.transform = "translate3d(" + (i % 2 ? off - 1000 : -off) + "px,0,0)";
      });
      ticking = false;
    };
    moveTape();
    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(moveTape);
    }, { passive: true });
  }

  // Scroll reveals
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduced) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("is-in"); });
  }

  // Photo upload previews (data: URLs only — nothing leaves the device)
  document.querySelectorAll("[data-upload]").forEach(function (zone) {
    var input = zone.querySelector("input[type=file]");
    var thumbs = document.getElementById(zone.getAttribute("data-upload"));
    var label = zone.querySelector("[data-upload-label]");
    if (!input) return;
    function show(files) {
      if (!thumbs) return;
      thumbs.innerHTML = "";
      Array.prototype.slice.call(files, 0, 6).forEach(function (f) {
        if (!/^image\//.test(f.type)) return;
        var r = new FileReader();
        r.onload = function () {
          var img = new Image();
          img.src = r.result;
          img.alt = "Selected photo: " + f.name;
          thumbs.appendChild(img);
        };
        r.readAsDataURL(f);
      });
      if (label) label.textContent = files.length ? files.length + (files.length === 1 ? " photo selected" : " photos selected") : label.getAttribute("data-default");
    }
    input.addEventListener("change", function () { show(input.files); });
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("is-drag"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("is-drag"); });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) {
        try { input.files = e.dataTransfer.files; } catch (err) { /* older browsers */ }
        show(e.dataTransfer.files);
      }
    });
  });


  // Mobile menu
  var toggle = document.querySelector(".menu-toggle");
  if (toggle && header) {
    toggle.addEventListener("click", function () {
      var open = !header.classList.contains("menu-open");
      header.classList.toggle("menu-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && header.classList.contains("menu-open")) {
        header.classList.remove("menu-open"); toggle.setAttribute("aria-expanded", "false"); toggle.focus();
      }
    });
  }

  // Tony — garment rail picker that routes to the quote form
  document.querySelectorAll("[data-picker]").forEach(function (pk) {
    var go = pk.querySelector("[data-picker-go]");
    var out = pk.querySelector("[data-picker-out]");
    function update() {
      var g = pk.querySelector("input[name=pick-garment]:checked");
      var gv = g ? g.value : "";
      pk.querySelectorAll(".jobs").forEach(function (j) { j.classList.toggle("is-active", j.getAttribute("data-for") === gv); });
      var jobs = [];
      var panel = pk.querySelector('.jobs[data-for="' + gv + '"]');
      if (panel) panel.querySelectorAll("input:checked").forEach(function (c) { jobs.push(c.value); });
      if (out) {
        out.textContent = "";
        var strong = document.createElement("strong");
        strong.textContent = gv || "Pick a garment";
        out.appendChild(strong);
        out.appendChild(document.createTextNode(jobs.length ? " — " + jobs.join(", ") : (gv ? " — now tick what needs doing" : "")));
      }
      if (go) {
        var q = [];
        if (gv) q.push("garment=" + encodeURIComponent(gv));
        if (jobs.length) q.push("job=" + encodeURIComponent(jobs.join("|")));
        go.setAttribute("href", "book.html" + (q.length ? "?" + q.join("&") : "") + "#quote");
      }
    }
    pk.addEventListener("change", update);
    update();
  });

  // Balmain — hem length studio
  document.querySelectorAll("[data-hem]").forEach(function (h) {
    var range = h.querySelector("input[type=range]");
    var skirt = h.querySelector(".skirt");
    var chalk = h.querySelector(".chalk");
    var marker = h.querySelector(".hem-marker");
    var out = h.querySelector("output");
    var note = h.querySelector("[data-hem-note]");
    var go = h.querySelector("[data-hem-go]");
    var stops = [
      ["Mini", "Mid-thigh — playful and short", 205],
      ["Above knee", "A clean, easy length for day", 235],
      ["Knee", "Classic and works almost anywhere", 262],
      ["Midi", "Just below the calf — elegant for events", 300],
      ["Ankle", "Shows the shoe — great for formal", 340],
      ["Floor", "Full length — measured with your shoes on", 368]
    ];
    function draw() {
      var s = stops[+range.value];
      var y = s[2], spread = (y - 130) * 0.32;
      var l = 72 - spread, r = 128 + spread;
      skirt.setAttribute("d", "M74 130 L126 130 L" + r.toFixed(1) + " " + y + " Q100 " + (y + 8) + " " + l.toFixed(1) + " " + y + " Z");
      chalk.setAttribute("x1", (l - 8).toFixed(1)); chalk.setAttribute("x2", (r + 8).toFixed(1));
      chalk.setAttribute("y1", y + 4); chalk.setAttribute("y2", y + 4);
      if (marker) marker.style.top = ((y + 4) / 390 * 100).toFixed(1) + "%";
      if (out) out.textContent = s[0];
      if (note) note.textContent = s[1];
      range.setAttribute("aria-valuetext", s[0]);
      if (go) go.setAttribute("href", "book.html?hem=" + encodeURIComponent(s[0]) + "#fitting");
    }
    range.addEventListener("input", draw);
    draw();
  });

  // Precision — fit guide with hotspots
  document.querySelectorAll("[data-fit]").forEach(function (f) {
    var panel = f.querySelector(".fit-panel");
    var go = f.querySelector("[data-fit-go]");
    function pick(btn) {
      f.querySelectorAll(".hs").forEach(function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
      panel.querySelector(".k").textContent = btn.getAttribute("data-k");
      panel.querySelector("h3").textContent = btn.getAttribute("data-t");
      panel.querySelector(".fit-desc").textContent = btn.getAttribute("data-d");
      panel.querySelector(".tagline").textContent = btn.getAttribute("data-g");
      if (go) go.setAttribute("href", "book.html?garment=" + encodeURIComponent(f.getAttribute("data-mode") === "gown" ? "Wedding dress" : "Suit") + "&area=" + encodeURIComponent(btn.getAttribute("data-t")) + "#request");
    }
    f.querySelectorAll(".hs").forEach(function (b) { b.addEventListener("click", function () { pick(b); }); });
    f.querySelectorAll("[data-mode-btn]").forEach(function (b) {
      b.addEventListener("click", function () {
        var m = b.getAttribute("data-mode-btn");
        f.setAttribute("data-mode", m);
        f.querySelectorAll("[data-mode-btn]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        pick(f.querySelector(".hs-" + m));
      });
    });
    pick(f.querySelector(".hs-suit"));
  });

  // Book pages — prefill from the home-page picker (query string, stays on device)
  if (window.URLSearchParams && location.search) {
    var qs = new URLSearchParams(location.search);
    var form = document.querySelector("form[data-preview]");
    if (form) {
      var g = qs.get("garment");
      if (g) {
        form.querySelectorAll("select[name=garment] option").forEach(function (o) { if (o.text.toLowerCase().indexOf(g.toLowerCase().split(" ")[0]) === 0) o.selected = true; });
        form.querySelectorAll("input[name=garment]").forEach(function (i) { if (i.value.toLowerCase().indexOf(g.toLowerCase().split(" ")[0]) === 0) i.checked = true; });
      }
      var j = qs.get("job");
      if (j) j.split("|").forEach(function (v) {
        form.querySelectorAll("input[name=job]").forEach(function (i) { if (i.value === v) i.checked = true; });
      });
      var hem = qs.get("hem"), area = qs.get("area");
      var ta = form.querySelector("textarea");
      if (ta && hem) ta.value = "Hem to " + hem.toLowerCase() + " length";
      if (ta && area) ta.value = area + " — ";
    }
  }

  // Multi-step forms
  document.querySelectorAll("[data-steps]").forEach(function (form) {
    var panes = form.querySelectorAll(".pane");
    var marks = form.querySelectorAll(".stepper li");
    var current = 0;
    function go(n) {
      // validate the pane we're leaving when moving forward
      if (n > current) {
        var fields = panes[current].querySelectorAll("input, select, textarea");
        for (var i = 0; i < fields.length; i++) {
          if (!fields[i].checkValidity()) { fields[i].reportValidity(); return; }
        }
      }
      current = Math.max(0, Math.min(panes.length - 1, n));
      panes.forEach(function (p, i) { p.classList.toggle("is-active", i === current); });
      marks.forEach(function (m, i) {
        m.classList.toggle("is-active", i === current);
        m.classList.toggle("is-done", i < current);
        if (i === current) m.setAttribute("aria-current", "step"); else m.removeAttribute("aria-current");
      });
      if (current === panes.length - 1) fillSummary();
      var head = panes[current].querySelector("h4, .legend, label");
      if (head && n !== 0) { panes[current].setAttribute("tabindex", "-1"); panes[current].focus({ preventScroll: true }); }
    }
    function fillSummary() {
      var out = form.querySelector("[data-summary]");
      if (!out) return;
      var rows = [];
      form.querySelectorAll("[data-sum]").forEach(function (el) {
        var v = "";
        if (el.tagName === "FIELDSET") {
          v = Array.prototype.map.call(el.querySelectorAll("input:checked"), function (c) { return c.value; }).join(", ");
        } else if (el.tagName === "SELECT") {
          v = el.value ? el.options[el.selectedIndex].text : "";
        } else {
          v = el.value;
        }
        if (v) rows.push([el.getAttribute("data-sum"), v]);
      });
      out.innerHTML = "";
      var dl = document.createElement("dl");
      rows.forEach(function (r) {
        var dt = document.createElement("dt"); dt.textContent = r[0];
        var dd = document.createElement("dd"); dd.textContent = r[1];
        dl.appendChild(dt); dl.appendChild(dd);
      });
      if (!rows.length) { var p = document.createElement("p"); p.textContent = "Your choices will appear here."; out.appendChild(p); }
      else out.appendChild(dl);
    }
    form.querySelectorAll("[data-next]").forEach(function (b) { b.addEventListener("click", function () { go(current + 1); }); });
    form.querySelectorAll("[data-prev]").forEach(function (b) { b.addEventListener("click", function () { go(current - 1); }); });
    go(0);
  });

  // Preview-only submit: never sends anything
  document.querySelectorAll("form[data-preview]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var status = form.querySelector(".form-status");
      if (status) {
        status.classList.add("is-shown");
        status.setAttribute("tabindex", "-1");
        status.focus({ preventScroll: true });
        status.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      }
    });
  });
})();
