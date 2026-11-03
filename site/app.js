/* Cyber Security Prep — static test runner.
 * No framework, no build step. Loads data/manifest.json, then data/<id>.json.
 * Progress, preferences and history live in localStorage under csp.* keys.
 */
(function () {
  "use strict";

  var KEY_ATTEMPT = "csp.attempt";
  var KEY_HISTORY = "csp.history";
  var KEY_PREFS = "csp.prefs";

  var manifest = [];
  var test = null;      // full test JSON of the running/last test
  var attempt = null;   // in-progress attempt
  var result = null;    // computed result after submit
  var pos = 0;          // index into attempt.order
  var ticker = null;
  var reviewFilter = "all";

  // ── tiny helpers ────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function show(name) {
    ["home", "test", "result", "history"].forEach(function (s) {
      $("screen-" + s).classList.toggle("hidden", s !== name);
    });
    window.scrollTo(0, 0);
  }
  function load(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* quota/private mode */ }
  }
  function drop(key) {
    try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
  }

  /* Escape first, then apply a deliberately tiny subset of Markdown.
     Question text is repo content, but escaping keeps a stray angle bracket
     from breaking the page. */
  function inlineMd(src) {
    var s = String(src == null ? "" : src)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    return s;
  }
  function paragraphs(node, src) {
    node.innerHTML = "";
    String(src == null ? "" : src).split(/\n{2,}/).forEach(function (chunk) {
      if (!chunk.trim()) return;
      var p = document.createElement("p");
      p.innerHTML = inlineMd(chunk.trim().replace(/\n/g, " "));
      node.appendChild(p);
    });
  }
  function shuffled(arr) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function clock(totalSec) {
    var s = Math.max(0, Math.round(totalSec));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    var mm = (h ? String(m).padStart(2, "0") : String(m));
    return (h ? h + ":" : "") + mm + ":" + String(sec).padStart(2, "0");
  }
  function human(sec) {
    var m = Math.floor(sec / 60);
    return m < 1 ? Math.round(sec) + "s" : m + " min " + (sec % 60 ? (sec % 60) + "s" : "");
  }
  function when(ts) {
    var d = new Date(ts);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  // ── preferences ─────────────────────────────────────────────────
  function readPrefs() {
    var mode = document.querySelector('input[name="timerMode"]:checked');
    return {
      timerMode: mode ? mode.value : "recommended",
      customMinutes: Math.max(1, parseInt($("customMinutes").value, 10) || 60),
      shuffleQuestions: $("shuffleQuestions").checked,
      shuffleOptions: $("shuffleOptions").checked
    };
  }
  function applyPrefs(p) {
    if (!p) return;
    var radio = document.querySelector('input[name="timerMode"][value="' + p.timerMode + '"]');
    if (radio) radio.checked = true;
    if (p.customMinutes) $("customMinutes").value = p.customMinutes;
    $("shuffleQuestions").checked = !!p.shuffleQuestions;
    $("shuffleOptions").checked = !!p.shuffleOptions;
  }

  // ── boot ────────────────────────────────────────────────────────
  function boot() {
    applyPrefs(load(KEY_PREFS, null));
    wire();
    fetch("data/manifest.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        manifest = (data && data.tests) || [];
        renderTests();
        offerResume();
      })
      .catch(function (err) {
        $("testList").innerHTML =
          '<div class="card"><div class="card-main"><div class="card-title">' +
          'Could not load tests</div><div class="card-desc">' + inlineMd(String(err.message)) +
          '. If you opened this file directly from disk, run a local server instead: ' +
          '<code>python3 -m http.server</code> inside the <code>dist/</code> folder.' +
          '</div></div></div>';
      });
    renderHistory();
  }

  function wire() {
    $("homeLink").addEventListener("click", goHome);
    document.querySelectorAll("[data-go]").forEach(function (b) {
      b.addEventListener("click", function () {
        var dest = b.getAttribute("data-go");
        if (dest === "home") goHome(); else { renderHistory(); show("history"); }
      });
    });

    $("prevBtn").addEventListener("click", function () { move(-1); });
    $("nextBtn").addEventListener("click", function () { move(1); });
    $("flagBtn").addEventListener("click", toggleFlag);
    $("submitBtn").addEventListener("click", confirmSubmit);
    $("retakeBtn").addEventListener("click", function () {
      if (test) startTest(test.id);
    });

    $("resumeBtn").addEventListener("click", resumeAttempt);
    $("discardBtn").addEventListener("click", function () {
      drop(KEY_ATTEMPT);
      $("resumeBanner").classList.add("hidden");
    });

    $("clearHistory").addEventListener("click", function () {
      if (confirm("Delete all stored attempts from this browser?")) {
        drop(KEY_HISTORY);
        renderHistory();
      }
    });

    document.querySelectorAll(".chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        reviewFilter = chip.getAttribute("data-filter");
        renderReview();
      });
    });

    document.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", function (e) {
      if (attempt && !attempt.submitted) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  function goHome() {
    stopTicker();
    show("home");
    renderTests();
    offerResume();
  }

  // ── home ────────────────────────────────────────────────────────
  function renderTests() {
    var box = $("testList");
    box.innerHTML = "";
    if (!manifest.length) {
      box.appendChild(el("p", "muted", "No tests found. Add a Markdown file under tests/."));
      return;
    }
    manifest.forEach(function (t) {
      var card = el("div", "card");
      var main = el("div", "card-main");
      main.appendChild(el("div", "card-title", t.title));
      if (t.objective) main.appendChild(el("div", "card-obj", t.objective));
      if (t.description) main.appendChild(el("div", "card-desc", t.description));

      var facts = el("div", "card-facts");
      facts.appendChild(el("span", null, t.questionCount + " questions"));
      if (t.recommendedMinutes) facts.appendChild(el("span", null, t.recommendedMinutes + " min recommended"));
      if (t.passPercent) facts.appendChild(el("span", null, "pass " + t.passPercent + "%"));
      var best = bestScore(t.id);
      if (best != null) facts.appendChild(el("span", null, "best " + best + "%"));
      main.appendChild(facts);

      if (t.paper) {
        var paper = el("a", "paperlink", "Printable paper and key");
        paper.href = t.paper;
        paper.target = "_blank";
        paper.rel = "noopener";
        paper.title = "Opens the full paper with the answer key at the end";
        main.appendChild(paper);
      }

      var go = el("button", "btn primary", "Start");
      go.type = "button";
      go.addEventListener("click", function () { startTest(t.id); });

      card.appendChild(main);
      card.appendChild(go);
      box.appendChild(card);
    });

    var rec = manifest.map(function (t) { return t.recommendedMinutes; })
      .filter(function (m) { return m > 0; });
    $("recHint").textContent = rec.length
      ? "(uses each test's own limit)" : "(no limit set on these tests)";
  }

  function offerResume() {
    var saved = load(KEY_ATTEMPT, null);
    var banner = $("resumeBanner");
    if (!saved || saved.submitted) { banner.classList.add("hidden"); return; }
    var meta = manifest.filter(function (t) { return t.id === saved.testId; })[0];
    var answered = Object.keys(saved.answers || {}).length;
    $("resumeDetail").textContent = (meta ? meta.title : saved.testId) +
      " — " + answered + " of " + saved.total + " answered";
    banner.classList.remove("hidden");
  }

  function resumeAttempt() {
    var saved = load(KEY_ATTEMPT, null);
    if (!saved) return;
    fetchTest(saved.testId).then(function (data) {
      test = data;
      attempt = saved;
      pos = 0;
      // Land on the first unanswered question.
      for (var i = 0; i < attempt.order.length; i++) {
        if (attempt.answers[attempt.order[i]] == null) { pos = i; break; }
      }
      openRunner();
    }).catch(function () {
      alert("That test is no longer available, so the saved attempt was discarded.");
      drop(KEY_ATTEMPT);
      goHome();
    });
  }

  function fetchTest(id) {
    return fetch("data/" + encodeURIComponent(id) + ".json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
  }

  // ── start ───────────────────────────────────────────────────────
  function startTest(id) {
    var prefs = readPrefs();
    save(KEY_PREFS, prefs);

    var existing = load(KEY_ATTEMPT, null);
    if (existing && !existing.submitted &&
        !confirm("Starting a new test discards the attempt already in progress. Continue?")) {
      return;
    }

    fetchTest(id).then(function (data) {
      test = data;
      var order = data.questions.map(function (q) { return q.n; });
      if (prefs.shuffleQuestions) order = shuffled(order);

      var optionOrder = {};
      if (prefs.shuffleOptions) {
        data.questions.forEach(function (q) {
          optionOrder[q.n] = shuffled(q.options.map(function (o) { return o.letter; }));
        });
      }

      var minutes = 0;
      if (prefs.timerMode === "recommended") minutes = data.recommendedMinutes || 0;
      else if (prefs.timerMode === "custom") minutes = prefs.customMinutes;

      attempt = {
        testId: data.id,
        title: data.title,
        total: data.questions.length,
        order: order,
        optionOrder: optionOrder,
        answers: {},
        flags: {},
        startedAt: Date.now(),
        endsAt: minutes > 0 ? Date.now() + minutes * 60000 : null,
        submitted: false
      };
      pos = 0;
      save(KEY_ATTEMPT, attempt);
      openRunner();
    }).catch(function (err) {
      alert("Could not load that test: " + err.message);
    });
  }

  function openRunner() {
    $("runTitle").textContent = test.title;
    $("totalCount").textContent = attempt.total;
    show("test");
    startTicker();
    renderQuestion();
  }

  // ── timer ───────────────────────────────────────────────────────
  function startTicker() {
    stopTicker();
    var box = $("timer");
    if (!attempt.endsAt) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    tick();
    ticker = setInterval(tick, 1000);
  }
  function stopTicker() {
    if (ticker) { clearInterval(ticker); ticker = null; }
  }
  function tick() {
    if (!attempt || !attempt.endsAt) return;
    var left = (attempt.endsAt - Date.now()) / 1000;
    var box = $("timer");
    $("timerValue").textContent = clock(left);
    box.classList.toggle("low", left <= 300 && left > 60);
    box.classList.toggle("critical", left <= 60);
    if (left <= 0) {
      stopTicker();
      submit(true);
    }
  }

  // ── question view ───────────────────────────────────────────────
  function currentQ() {
    var n = attempt.order[pos];
    return test.questions.filter(function (q) { return q.n === n; })[0];
  }

  function orderedOptions(q) {
    var custom = attempt.optionOrder && attempt.optionOrder[q.n];
    if (!custom) return q.options;
    return custom.map(function (letter) {
      return q.options.filter(function (o) { return o.letter === letter; })[0];
    }).filter(Boolean);
  }

  function renderQuestion() {
    var q = currentQ();
    $("runSection").textContent = q.section || "";
    $("qPosition").textContent = "Question " + (pos + 1) + " of " + attempt.total;
    $("flagTag").classList.toggle("hidden", !attempt.flags[q.n]);
    $("flagBtn").textContent = attempt.flags[q.n] ? "Remove flag" : "Flag for review";
    paragraphs($("qStem"), q.stem);

    var box = $("qOptions");
    box.innerHTML = "";
    orderedOptions(q).forEach(function (o) {
      var b = el("button", "opt");
      b.type = "button";
      b.setAttribute("role", "radio");
      var chosen = attempt.answers[q.n] === o.letter;
      b.setAttribute("aria-checked", chosen ? "true" : "false");
      if (chosen) b.classList.add("sel");
      var letter = el("span", "letter", o.letter + ".");
      var txt = el("span");
      txt.innerHTML = inlineMd(o.text);
      b.appendChild(letter);
      b.appendChild(txt);
      b.addEventListener("click", function () { choose(q.n, o.letter); });
      box.appendChild(b);
    });

    $("prevBtn").disabled = pos === 0;
    $("nextBtn").disabled = pos === attempt.total - 1;
    updateCounters();
    renderNavGrid();
  }

  function choose(n, letter) {
    // Clicking the selected option again clears it, so a guess can be undone.
    if (attempt.answers[n] === letter) delete attempt.answers[n];
    else attempt.answers[n] = letter;
    save(KEY_ATTEMPT, attempt);
    renderQuestion();
  }

  function toggleFlag() {
    var q = currentQ();
    if (attempt.flags[q.n]) delete attempt.flags[q.n];
    else attempt.flags[q.n] = true;
    save(KEY_ATTEMPT, attempt);
    renderQuestion();
  }

  function move(delta) {
    var next = pos + delta;
    if (next < 0 || next >= attempt.total) return;
    pos = next;
    renderQuestion();
  }

  function updateCounters() {
    var answered = Object.keys(attempt.answers).length;
    $("answeredCount").textContent = answered;
    $("progressBar").style.width = (answered / attempt.total * 100) + "%";
  }

  function renderNavGrid() {
    var grid = $("navGrid");
    grid.innerHTML = "";
    attempt.order.forEach(function (n, i) {
      var cell = el("button", "cell", String(i + 1));
      cell.type = "button";
      if (attempt.answers[n] != null) cell.classList.add("answered");
      if (attempt.flags[n]) cell.classList.add("flagged");
      if (i === pos) cell.classList.add("current");
      cell.title = "Question " + (i + 1) +
        (attempt.answers[n] != null ? " — answered " + attempt.answers[n] : " — unanswered");
      cell.addEventListener("click", function () { pos = i; renderQuestion(); });
      grid.appendChild(cell);
    });
  }

  function onKey(e) {
    if ($("screen-test").classList.contains("hidden")) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowRight") { move(1); return; }
    if (e.key === "ArrowLeft") { move(-1); return; }
    if (e.key.toLowerCase() === "f") { toggleFlag(); return; }
    var q = currentQ();
    if (!q) return;
    var opts = orderedOptions(q);
    var idx = -1;
    if (/^[1-9]$/.test(e.key)) idx = parseInt(e.key, 10) - 1;
    else if (/^[a-zA-Z]$/.test(e.key)) {
      idx = opts.map(function (o) { return o.letter; }).indexOf(e.key.toUpperCase());
    }
    if (idx >= 0 && idx < opts.length) choose(q.n, opts[idx].letter);
  }

  // ── submit ──────────────────────────────────────────────────────
  function confirmSubmit() {
    var blank = attempt.total - Object.keys(attempt.answers).length;
    var msg = blank > 0
      ? blank + " question" + (blank === 1 ? " is" : "s are") +
        " still unanswered. Submit anyway?"
      : "Submit the test and reveal the answers?";
    if (confirm(msg)) submit(false);
  }

  function submit(auto) {
    stopTicker();
    attempt.submitted = true;
    var seconds = Math.round((Date.now() - attempt.startedAt) / 1000);

    var rows = test.questions.map(function (q) {
      var given = attempt.answers[q.n] || null;
      return {
        q: q,
        given: given,
        correct: given != null && given === q.answer,
        blank: given == null,
        flagged: !!attempt.flags[q.n]
      };
    });
    // Present review in the order the candidate actually saw.
    rows.sort(function (a, b) {
      return attempt.order.indexOf(a.q.n) - attempt.order.indexOf(b.q.n);
    });

    var right = rows.filter(function (r) { return r.correct; }).length;
    var pct = Math.round(right / rows.length * 100);
    var passMark = test.passPercent || 0;

    result = {
      rows: rows,
      correct: right,
      total: rows.length,
      pct: pct,
      passed: passMark ? pct >= passMark : null,
      seconds: seconds,
      auto: !!auto
    };

    var history = load(KEY_HISTORY, []);
    history.unshift({
      testId: test.id,
      title: test.title,
      correct: right,
      total: rows.length,
      pct: pct,
      passed: result.passed,
      seconds: seconds,
      finishedAt: Date.now()
    });
    save(KEY_HISTORY, history.slice(0, 100));
    drop(KEY_ATTEMPT);

    renderResult();
    show("result");
  }

  // ── results ─────────────────────────────────────────────────────
  function renderResult() {
    var card = $("scoreCard");
    card.className = "scorecard" + (result.passed === true ? " pass" :
      result.passed === false ? " fail" : "");
    card.innerHTML = "";

    card.appendChild(el("div", "score-pct", result.pct + "%"));
    var line = el("div");
    line.appendChild(el("span", null,
      result.correct + " of " + result.total + " correct"));
    if (result.passed !== null) {
      line.appendChild(document.createTextNode(" — "));
      line.appendChild(el("span", "verdict " + (result.passed ? "pass" : "fail"),
        result.passed ? "PASS" : "FAIL"));
      line.appendChild(document.createTextNode(
        " (pass mark " + test.passPercent + "%)"));
    }
    card.appendChild(line);

    var facts = el("div", "score-facts");
    facts.textContent = "Time taken " + human(result.seconds) +
      (result.auto ? " — submitted automatically when the timer ran out." : "");
    card.appendChild(facts);

    renderBreakdown();
    renderReview();
  }

  function renderBreakdown() {
    var box = $("sectionBreakdown");
    box.innerHTML = "";
    if (!test.sections || test.sections.length < 2) return;

    var table = el("table", "breakdown");
    var head = el("tr");
    ["Section", "Correct", "Score"].forEach(function (h, i) {
      var th = el("th", i ? "num" : null, h);
      head.appendChild(th);
    });
    table.appendChild(head);

    test.sections.forEach(function (name) {
      var rows = result.rows.filter(function (r) { return r.q.section === name; });
      if (!rows.length) return;
      var right = rows.filter(function (r) { return r.correct; }).length;
      var tr = el("tr");
      tr.appendChild(el("td", null, name));
      tr.appendChild(el("td", "num", right + " / " + rows.length));
      tr.appendChild(el("td", "num", Math.round(right / rows.length * 100) + "%"));
      table.appendChild(tr);
    });

    box.appendChild(el("h3", null, "By section"));
    box.appendChild(table);
  }

  function renderReview() {
    var box = $("reviewList");
    box.innerHTML = "";
    var rows = result.rows.filter(function (r) {
      if (reviewFilter === "wrong") return !r.correct && !r.blank;
      if (reviewFilter === "right") return r.correct;
      if (reviewFilter === "flagged") return r.flagged;
      if (reviewFilter === "blank") return r.blank;
      return true;
    });

    if (!rows.length) {
      box.appendChild(el("p", "muted", "Nothing matches that filter."));
      return;
    }

    rows.forEach(function (r) {
      var state = r.blank ? "blank" : (r.correct ? "right" : "wrong");
      var item = el("div", "ritem " + state);

      var head = el("div", "rhead");
      head.appendChild(el("span", null, r.q.label || ("Question " + r.q.n)));
      head.appendChild(el("span", "tag " + state,
        r.blank ? "Not answered" : (r.correct ? "Correct" : "Incorrect")));
      if (r.flagged) head.appendChild(el("span", "tag blank", "Flagged"));
      item.appendChild(head);

      var stem = el("div", "stem");
      paragraphs(stem, r.q.stem);
      item.appendChild(stem);

      r.q.options.forEach(function (o) {
        var cls = "ropt";
        var note = "";
        if (o.letter === r.q.answer) { cls += " correct"; note = "Correct answer"; }
        if (o.letter === r.given && o.letter !== r.q.answer) {
          cls += " chosen-wrong"; note = "Your answer";
        } else if (o.letter === r.given) {
          note = "Your answer";
        }
        var row = el("div", cls);
        row.appendChild(el("span", "letter", o.letter + "."));
        var txt = el("span");
        txt.innerHTML = inlineMd(o.text);
        row.appendChild(txt);
        if (note) row.appendChild(el("span", "mark", note));
        item.appendChild(row);
      });

      if (r.q.explain) {
        var ex = el("div", "explain");
        var lbl = el("strong", "lbl", "Why");
        ex.appendChild(lbl);
        var body = el("div");
        paragraphs(body, r.q.explain);
        ex.appendChild(body);
        item.appendChild(ex);
      }

      box.appendChild(item);
    });
  }

  // ── history ─────────────────────────────────────────────────────
  function bestScore(testId) {
    var rows = load(KEY_HISTORY, []).filter(function (h) { return h.testId === testId; });
    if (!rows.length) return null;
    return rows.reduce(function (m, h) { return Math.max(m, h.pct); }, 0);
  }

  function renderHistory() {
    var box = $("historyList");
    var rows = load(KEY_HISTORY, []);
    box.innerHTML = "";
    if (!rows.length) {
      box.appendChild(el("p", "muted", "No attempts recorded yet."));
      $("clearHistory").classList.add("hidden");
      return;
    }
    $("clearHistory").classList.remove("hidden");
    rows.forEach(function (h) {
      var row = el("div", "hrow");
      var left = el("div");
      left.appendChild(el("div", null, h.title));
      left.appendChild(el("div", "muted", when(h.finishedAt) + " — " + human(h.seconds)));
      var right = el("div");
      right.appendChild(el("div", "hscore " + (h.passed === true ? "pass" :
        h.passed === false ? "fail" : ""), h.pct + "%"));
      right.appendChild(el("div", "muted", h.correct + " / " + h.total));
      row.appendChild(left);
      row.appendChild(right);
      box.appendChild(row);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
