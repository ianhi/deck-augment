// Crosswordese — back-side card script.
//
// Runs immediately after the front content (which itself was included via
// the FrontSide directive above). The front JS has already run and used
// the cached state to render the same active clue / revealed hints /
// revealed letters that were on the front. This script:
//   1. Replaces the underscore pattern with the full answer.
//   2. Hides the hint row and collapses the extra-clues reservation so the
//      back-only content (definition, all clues) sits close under the
//      active clue.
//
// No need to mark state "consumed" — the front JS uses the back-marker
// element to detect back renders, and always creates fresh state on a
// normal front render, so each new review starts clean.
//
// CRITICAL: do NOT write the mustache double-brace sequence in this file,
// even inside comments. The build script rejects any occurrence.

(function () {
  var pat = document.getElementById("pattern");
  if (pat) {
    var answer = pat.getAttribute("data-answer") || "";
    pat.innerText = answer.split("").join(" ");
    pat.classList.add("revealed");
  }
  var hr = document.getElementById("hint-row");
  if (hr) hr.style.display = "none";
  var ex = document.getElementById("extra-clues");
  if (ex) ex.style.minHeight = "0";
})();
