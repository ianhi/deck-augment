// Crosswordese — front-side card script.
//
// Key invariant: every NEW front render = fresh state (new shuffle, no
// revealed letters, no revealed extra clues). A back-side render is
// detected via the back-marker element (only the back template emits it);
// in that case we reuse the cached state so the back shows the same active
// clue / revealed hints / revealed letters as the front.
//
// Persistence within one review uses sessionStorage, keyed by answer.
//
// CRITICAL: do NOT write the mustache double-brace sequence in this file,
// even inside comments. Anki substitutes those tokens inside the script
// tag and the substituted content can contain a closing script tag,
// breaking the entire render. The build script enforces this.

(function () {
  var pat = document.getElementById("pattern");
  if (!pat) return;
  var answer = pat.getAttribute("data-answer") || "";
  var STKEY = "cw3_" + answer;
  var isBackRender = !!document.getElementById("back-marker");

  function loadState() {
    try {
      var s = sessionStorage.getItem(STKEY);
      return s ? JSON.parse(s) : null;
    } catch (e) {
      return null;
    }
  }

  function saveState(s) {
    try {
      sessionStorage.setItem(STKEY, JSON.stringify(s));
    } catch (e) {}
  }

  // Fisher-Yates in-place shuffle.
  function shuffle(arr) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = arr[i];
      arr[i] = arr[j];
      arr[j] = tmp;
    }
  }

  function freshState() {
    var poolNodes = document.querySelectorAll("#clue-pool .clue-pool-item");
    var pool = [];
    for (var i = 0; i < poolNodes.length; i++) {
      // textContent (not innerText): Chromium/Qt WebEngine returns "" from
      // innerText on elements inside display:none subtrees, but textContent
      // is independent of CSS visibility.
      var txt = (poolNodes[i].textContent || "").trim();
      if (txt) pool.push(txt);
    }
    shuffle(pool);

    var letterOrder = [];
    for (var p = 0; p < answer.length; p++) letterOrder.push(p);
    shuffle(letterOrder);

    return {
      pool: pool,
      revealedClues: 1,
      letterOrder: letterOrder,
      revealedLetters: 0,
    };
  }

  var st;
  if (isBackRender) {
    st = loadState() || freshState();
  } else {
    st = freshState();
    saveState(st);
  }

  // -- render --
  var ac = document.getElementById("active-clue");
  ac.innerText = st.pool[0] || "(no clue available)";

  var ex = document.getElementById("extra-clues");
  for (var k = 1; k < st.revealedClues; k++) {
    var d = document.createElement("div");
    d.className = "extra-clue";
    d.innerText = st.pool[k];
    ex.appendChild(d);
  }

  function renderPattern() {
    var shown = {};
    for (var r = 0; r < st.revealedLetters; r++) {
      shown[st.letterOrder[r]] = 1;
    }
    var out = [];
    for (var k2 = 0; k2 < answer.length; k2++) {
      out.push(shown[k2] ? answer[k2] : "_");
    }
    pat.innerText = out.join(" ");
  }
  renderPattern();

  // -- hint buttons --
  var moreClue = document.getElementById("more-clue");
  var moreLetter = document.getElementById("more-letter");
  if (st.revealedClues >= st.pool.length) moreClue.classList.add("spent");
  if (st.revealedLetters >= answer.length) moreLetter.classList.add("spent");

  // Stop AnkiDroid's tap-to-reveal-back gesture from firing when the user
  // taps a hint button. We only call stopPropagation — NOT preventDefault,
  // because preventDefault on touchstart/touchend suppresses the browser's
  // click synthesis and the buttons stop working entirely.
  function stopBubble(ev) {
    if (ev) ev.stopPropagation();
  }

  moreClue.addEventListener("click", function (ev) {
    stopBubble(ev);
    if (st.revealedClues >= st.pool.length) return;
    var d2 = document.createElement("div");
    d2.className = "extra-clue";
    d2.innerText = st.pool[st.revealedClues];
    ex.appendChild(d2);
    st.revealedClues++;
    saveState(st);
    if (st.revealedClues >= st.pool.length) moreClue.classList.add("spent");
  });

  moreLetter.addEventListener("click", function (ev) {
    stopBubble(ev);
    if (st.revealedLetters >= answer.length) return;
    st.revealedLetters++;
    renderPattern();
    saveState(st);
    if (st.revealedLetters >= answer.length) moreLetter.classList.add("spent");
  });

  // Cover every phase AnkiDroid's gesture detector might hook into. We
  // only stopPropagation — never preventDefault — so the browser still
  // synthesizes the click event that drives the logic above.
  ["touchstart", "touchend", "pointerdown", "pointerup", "mousedown"].forEach(
    function (type) {
      moreClue.addEventListener(type, stopBubble);
      moreLetter.addEventListener(type, stopBubble);
    },
  );
})();
