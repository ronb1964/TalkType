/* TuxTalk website: the hold-F8 demo, copy buttons and the light/dark switch.
   No libraries; everything here works without it too (the page is complete
   at rest, this only adds the interaction). */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Light / dark switch ---------- */
  var root = document.documentElement;
  var themeBtn = document.getElementById("theme-btn");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      // Work out what's showing now (a saved choice, or the system setting).
      var current = root.getAttribute("data-theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var next = current === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("tuxtalk-theme", next); } catch (e) { /* private window: fine */ }
    });
  }

  /* ---------- Copy buttons on the install commands ---------- */
  document.querySelectorAll(".cmd .copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.parentElement.querySelector("code");
      var text = code.textContent;
      var done = function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy"; }, 1600);
      };
      var selectIt = function () {
        // Clipboard refused: select the text so Ctrl+C works.
        var range = document.createRange();
        range.selectNodeContents(code);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        btn.textContent = "Press Ctrl+C";
        setTimeout(function () { btn.textContent = "Copy"; }, 2400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, selectIt);
      } else {
        selectIt();
      }
    });
  });

  /* ---------- Screenshot strip buttons ---------- */
  var strip = document.querySelector(".strip");
  if (strip) {
    var btns = document.querySelectorAll(".strip-btn");
    var updateBtns = function () {
      btns[0].disabled = strip.scrollLeft < 8;
      btns[1].disabled = strip.scrollLeft + strip.clientWidth > strip.scrollWidth - 8;
    };
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        strip.scrollBy({ left: Number(b.getAttribute("data-dir")) * strip.clientWidth * 0.8, behavior: reduceMotion ? "auto" : "smooth" });
      });
    });
    strip.addEventListener("scroll", updateBtns, { passive: true });
    updateBtns();
  }

  /* ---------- The story: switch the sticky stage as each step scrolls by ---------- */
  var stage = document.getElementById("stage");
  var stepList = document.querySelector(".steps");
  if (stage && stepList && "IntersectionObserver" in window) {
    stage.classList.add("js");
    stepList.classList.add("js");
    stage.setAttribute("data-step", "1");
    var steps = stepList.querySelectorAll("li");
    var watch = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        steps.forEach(function (li) { li.classList.toggle("active", li === en.target); });
        stage.setAttribute("data-step", en.target.getAttribute("data-step"));
      });
    }, { rootMargin: "-45% 0px -45% 0px" });
    steps.forEach(function (li) { watch.observe(li); });
    steps[0].classList.add("active");
  }

  /* ---------- The F8 demo ---------- */
  var key = document.getElementById("key");
  var doc = document.getElementById("doc");
  if (!key || !doc) return;

  var indicator = document.getElementById("indicator");
  var orb = document.getElementById("orb");
  var timerEl = document.getElementById("timer");
  var said = document.getElementById("said");
  var announce = document.getElementById("announce");

  // Each example: what you say, and what TuxTalk types. "para" starts a new
  // paragraph; "\n" is a line break. These match real TuxTalk behavior
  // (voice commands and email addresses need no AI).
  var examples = [
    { say: "send the plans to john at gmail dot com", para: true, type: "Send the plans to john@gmail.com." },
    { say: "new paragraph could we meet on Thursday at four question mark", para: true, type: "Could we meet on Thursday at four?" },
    { say: "I'll bring the parts list", para: false, type: " I'll bring the parts list." },
    { say: "new paragraph thanks comma new line Ron", para: true, type: "Thanks,\nRon" }
  ];
  var initialHTML = doc.innerHTML;
  var next = 0;
  var state = "idle";          // idle | listening | typing
  var touched = false;         // stop the auto demo once someone tries it
  var wordTimer = null, clockTimer = null, levelRaf = null, startedAt = 0;
  var shownWords = 0;

  function caret() {
    var c = doc.querySelector(".caret");
    if (!c) {
      c = document.createElement("span");
      c.className = "caret";
      c.setAttribute("aria-hidden", "true");
    }
    return c;
  }

  function lastPara() {
    var ps = doc.querySelectorAll("p");
    return ps[ps.length - 1];
  }

  function setSaid(label, words) {
    said.innerHTML = "";
    var l = document.createElement("span");
    l.className = "label";
    l.textContent = label;
    said.appendChild(l);
    if (words !== null) {
      var q = document.createElement("q");
      q.textContent = words;
      said.appendChild(q);
    }
  }

  // The orb pulses with a made-up voice level while "listening".
  function animateLevel() {
    var t = performance.now() / 1000;
    var lvl = 0.45 + 0.3 * Math.sin(t * 9.1) * Math.sin(t * 2.3) + 0.25 * Math.random();
    orb.style.setProperty("--lvl", Math.max(0, Math.min(1, lvl)).toFixed(2));
    levelRaf = requestAnimationFrame(animateLevel);
  }

  function start() {
    if (state !== "idle") return;
    state = "listening";
    key.classList.add("down");
    indicator.classList.add("on");
    startedAt = performance.now();
    timerEl.textContent = "0:00";
    clockTimer = setInterval(function () {
      var s = Math.floor((performance.now() - startedAt) / 1000);
      timerEl.textContent = "0:" + (s < 10 ? "0" : "") + s;
    }, 250);
    if (!reduceMotion) animateLevel();

    // Reveal the spoken words at about talking speed.
    var words = examples[next].say.split(" ");
    shownWords = 0;
    setSaid("You say", "");
    var q = said.querySelector("q");
    wordTimer = setInterval(function () {
      if (shownWords < words.length) {
        shownWords++;
        q.textContent = words.slice(0, shownWords).join(" ");
      }
    }, reduceMotion ? 1 : 230);
  }

  function stop() {
    if (state !== "listening") return;
    clearInterval(wordTimer);
    clearInterval(clockTimer);
    cancelAnimationFrame(levelRaf);
    key.classList.remove("down");
    indicator.classList.remove("on");

    var ex = examples[next];
    var held = performance.now() - startedAt;
    // A tap that's too short to say anything: TuxTalk types nothing either.
    if (held < 250) {
      state = "idle";
      setSaid("Too quick", null);
      said.appendChild(document.createTextNode("Hold the key down while you talk."));
      return;
    }
    setSaid("You said", ex.say);
    typeOut(ex);
  }

  // Type the result a character at a time, the way it lands in a real window.
  function typeOut(ex) {
    state = "typing";
    if (next === 0 && doc.querySelectorAll("p").length > 2) doc.innerHTML = initialHTML;
    var c = caret();
    var target;
    if (ex.para) {
      target = document.createElement("p");
      doc.appendChild(target);
    } else {
      target = lastPara();
    }
    target.appendChild(c);

    var chars = Array.from(ex.type);
    var i = 0;
    function step() {
      if (i >= chars.length) {
        state = "idle";
        next = (next + 1) % examples.length;
        announce.textContent = "Typed: " + ex.type.replace("\n", " ");
        // Back to the start after the last example.
        if (next === 0) setTimeout(function () { if (state === "idle") { doc.innerHTML = initialHTML; } }, 2600);
        return;
      }
      var ch = chars[i++];
      if (ch === "\n") {
        target.insertBefore(document.createElement("br"), c);
      } else {
        var prev = c.previousSibling;
        if (prev && prev.nodeType === 3) prev.textContent += ch;
        else target.insertBefore(document.createTextNode(ch), c);
      }
      doc.scrollTop = doc.scrollHeight;  // keep the newest line in view
      if (reduceMotion) step(); else setTimeout(step, 16);
    }
    setTimeout(step, reduceMotion ? 0 : 280);
  }

  // Pointer: press and hold the key on the page.
  key.addEventListener("pointerdown", function (e) {
    touched = true;
    if (e.button !== undefined && e.button !== 0) return;
    try { key.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
    e.preventDefault();
    start();
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (ev) {
    key.addEventListener(ev, stop);
  });
  key.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  // Keyboard on the focused key: Space or Enter, held.
  key.addEventListener("keydown", function (e) {
    if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); touched = true; start(); }
  });
  key.addEventListener("keyup", function (e) {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); stop(); }
  });
  key.addEventListener("click", function (e) { e.preventDefault(); });

  // The real F8 anywhere on the page.
  window.addEventListener("keydown", function (e) {
    if (e.key === "F8" && !e.repeat) { e.preventDefault(); touched = true; start(); }
  });
  window.addEventListener("keyup", function (e) {
    if (e.key === "F8") { e.preventDefault(); stop(); }
  });
  window.addEventListener("blur", stop);

  // Play one example by itself the first time the key comes into view, so
  // you see what happens without having to find the key first.
  function autoDemo() {
    if (touched || document.hidden || state !== "idle") return;
    start();
    setTimeout(function () { if (!touched) stop(); }, 2700);
  }
  if (!reduceMotion && "IntersectionObserver" in window) {
    var seen = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        seen.disconnect();
        setTimeout(autoDemo, 900);
      }
    }, { threshold: 0.9 });
    seen.observe(key);
  }
})();
