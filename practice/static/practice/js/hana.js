/* Hana Seo, the CyberQuest mentor. One inline SVG cloned from #cq-hana-tpl;
   setExpression swaps the class and the brow / mouth paths (values from the design's EXP table). */
(function () {
  "use strict";

  var NB = { bl: "M92 97 Q103 91 115 95", br: "M125 95 Q137 91 148 97" };
  var HAPPY = { bl: "M92 94 Q103 87 115 92", br: "M125 92 Q137 87 148 94", m: "M111 145 Q120 158 129 145 Z", f: "#B5434F", blush: 0.75, closed: true };
  var EXP = {
    neutral: { bl: NB.bl, br: NB.br, m: "M114 148 Q120 151 126 148", f: "none", blush: 0.35 },
    smile: { bl: NB.bl, br: NB.br, m: "M112 147 Q120 154 128 147", f: "none", blush: 0.55 },
    talk: { bl: NB.bl, br: NB.br, m: "M113 147 Q120 155 127 147 Z", f: "#B5434F", blush: 0.45 },
    think: { bl: "M92 94 Q103 88 115 93", br: "M125 97 Q137 95 148 98", m: "M115 149 L125 148", f: "none", blush: 0.3 },
    correct: HAPPY,
    happy: HAPPY,
    wrong: { bl: "M92 96 Q103 95 115 90", br: "M125 90 Q137 95 148 96", m: "M113 151 Q120 146 127 151", f: "none", blush: 0.2 },
    surprised: { bl: "M92 92 Q103 85 115 90", br: "M125 90 Q137 85 148 92", m: "M117 149 a3 4 0 1 0 6 0 a3 4 0 1 0 -6 0", f: "#B5434F", blush: 0.3 }
  };

  /** Fill an avatar box with a fresh Hana. Returns the .hana element. */
  function mount(box) {
    var tpl = document.getElementById("cq-hana-tpl");
    if (!tpl || !box) return null;
    box.innerHTML = "";
    box.appendChild(tpl.content.cloneNode(true));
    var el = box.querySelector(".hana");
    setExpression(el, box.getAttribute("data-expression") || "neutral");
    return el;
  }

  /** Change Hana's face: smile | talk | think | correct | wrong | happy | surprised | neutral. */
  function setExpression(el, name) {
    if (!el) return;
    if (!el.classList.contains("hana")) el = el.querySelector(".hana");
    if (!el) return;
    var e = EXP[name] || EXP.neutral;
    // Restart one-shot animations (nod, shake) when the same face is set twice.
    el.setAttribute("class", "hana");
    void el.offsetWidth;
    el.setAttribute("class", "hana " + (EXP[name] ? name : "neutral"));
    el.querySelector(".hana-brow-l").setAttribute("d", e.bl);
    el.querySelector(".hana-brow-r").setAttribute("d", e.br);
    var mouth = el.querySelector(".hana-mouth");
    mouth.setAttribute("d", e.m);
    mouth.setAttribute("fill", e.f);
    el.querySelector(".hana-blush").setAttribute("opacity", String(e.blush));
    el.querySelector(".hana-eyes-open").style.display = e.closed ? "none" : "";
    el.querySelector(".hana-eyes-closed").style.display = e.closed ? "" : "none";
  }

  window.CQHana = { mount: mount, setExpression: setExpression };
})();
