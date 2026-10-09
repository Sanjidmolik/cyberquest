(function () {
  var editor = document.getElementById("cert-editor");
  var artwork = document.getElementById("cert-artwork");
  var hidden = document.getElementById("id_field_config");
  var source = document.getElementById("editor-config");
  if (!editor || !artwork || !hidden || !source) return;

  var pageWidth = parseFloat(editor.dataset.pageWidth);
  var pageHeight = parseFloat(editor.dataset.pageHeight);
  var config = {};
  try {
    var posted = JSON.parse(hidden.value || "{}");
    config = posted && Object.keys(posted).length ? posted : JSON.parse(source.textContent);
  } catch (error) {
    config = JSON.parse(source.textContent);
  }
  ["name", "score", "date", "certificate_id", "qr"].forEach(function (key) {
    config[key] = config[key] || {};
  });

  var selected = "name";
  var boxes = {};
  editor.querySelectorAll(".ops-field-box").forEach(function (box) {
    boxes[box.dataset.field] = box;
  });
  var inputs = {
    w: document.getElementById("field-w"),
    h: document.getElementById("field-h"),
    size: document.getElementById("field-size"),
    align: document.getElementById("field-align"),
    color: document.getElementById("field-color"),
  };

  function toPage(pixel, display, page) {
    if (!display) return 0;
    return Math.round((pixel * page / display) * 10) / 10;
  }

  function writeConfig() {
    hidden.value = JSON.stringify(config);
  }

  function specOf(key) {
    return config[key];
  }

  function paint() {
    var width = artwork.clientWidth || artwork.naturalWidth;
    var height = artwork.clientHeight || artwork.naturalHeight;
    if (!width || !height || !pageWidth || !pageHeight) return;
    Object.keys(boxes).forEach(function (key) {
      var spec = specOf(key);
      var box = boxes[key];
      var x = parseFloat(spec.x || 0) * (width / pageWidth);
      var y = parseFloat(spec.y || 0) * (height / pageHeight);
      var boxW;
      var boxH;
      if (key === "qr") {
        var size = parseFloat(spec.size || spec.w || 40);
        boxW = size * (width / pageWidth);
        boxH = size * (height / pageHeight);
      } else {
        boxW = parseFloat(spec.w || 40) * (width / pageWidth);
        boxH = parseFloat(spec.h || 20) * (height / pageHeight);
      }
      box.style.left = x + "px";
      box.style.top = y + "px";
      box.style.width = Math.max(boxW, 12) + "px";
      box.style.height = Math.max(boxH, 12) + "px";
      box.classList.toggle("is-selected", key === selected);
      if (spec.color) box.style.color = spec.color;
      box.style.textAlign = spec.align === 0 ? "left" : spec.align === 2 ? "right" : "center";
    });
  }

  function fillInputs() {
    var spec = specOf(selected);
    if (selected === "qr") {
      inputs.w.value = spec.size != null ? spec.size : "";
      inputs.h.value = spec.size != null ? spec.size : "";
      inputs.size.value = "";
      inputs.size.disabled = true;
      inputs.align.disabled = true;
    } else {
      inputs.w.value = spec.w != null ? spec.w : "";
      inputs.h.value = spec.h != null ? spec.h : "";
      inputs.size.value = spec.fontsize != null ? spec.fontsize : "";
      inputs.size.disabled = false;
      inputs.align.disabled = false;
    }
    inputs.align.value = String(spec.align != null ? spec.align : 1);
    inputs.color.value = /^#[0-9A-Fa-f]{6}$/.test(spec.color || "") ? spec.color : "#f4eeff";
    editor.querySelectorAll(".ops-field-chip").forEach(function (chip) {
      chip.classList.toggle("is-selected", chip.dataset.field === selected);
    });
    paint();
  }

  function readInputs() {
    var spec = specOf(selected);
    if (selected === "qr") {
      var size = parseFloat(inputs.w.value || inputs.h.value || "0");
      spec.size = size;
      spec.w = size;
      spec.h = size;
    } else {
      spec.w = parseFloat(inputs.w.value || "0");
      spec.h = parseFloat(inputs.h.value || "0");
      spec.fontsize = parseFloat(inputs.size.value || "0");
      spec.align = parseInt(inputs.align.value, 10);
      spec.color = inputs.color.value;
    }
    writeConfig();
    paint();
  }

  function selectField(key) {
    selected = key;
    fillInputs();
  }

  editor.querySelectorAll(".ops-field-chip").forEach(function (chip) {
    chip.addEventListener("click", function () { selectField(chip.dataset.field); });
  });
  Object.keys(inputs).forEach(function (key) {
    inputs[key].addEventListener("input", readInputs);
  });

  var drag = null;
  Object.keys(boxes).forEach(function (key) {
    var box = boxes[key];
    box.addEventListener("pointerdown", function (event) {
      if (event.target.classList.contains("ops-resize")) return;
      selectField(key);
      var spec = specOf(key);
      drag = {
        mode: "move",
        key: key,
        pointer: event.pointerId,
        originX: event.clientX,
        originY: event.clientY,
        x: parseFloat(spec.x || 0),
        y: parseFloat(spec.y || 0),
      };
      box.setPointerCapture(event.pointerId);
    });
    box.querySelector(".ops-resize").addEventListener("pointerdown", function (event) {
      event.stopPropagation();
      selectField(key);
      var spec = specOf(key);
      drag = {
        mode: "resize",
        key: key,
        pointer: event.pointerId,
        originX: event.clientX,
        originY: event.clientY,
        w: parseFloat(key === "qr" ? (spec.size || spec.w || 40) : (spec.w || 40)),
        h: parseFloat(key === "qr" ? (spec.size || spec.h || 40) : (spec.h || 20)),
      };
      box.setPointerCapture(event.pointerId);
    });
    box.addEventListener("pointermove", function (event) {
      if (!drag || drag.pointer !== event.pointerId || drag.key !== key) return;
      var width = artwork.clientWidth;
      var height = artwork.clientHeight;
      if (!width || !height) return;
      var spec = specOf(key);
      if (drag.mode === "move") {
        spec.x = toPage((drag.x * width / pageWidth) + (event.clientX - drag.originX), width, pageWidth);
        spec.y = toPage((drag.y * height / pageHeight) + (event.clientY - drag.originY), height, pageHeight);
      } else {
        var nextW = Math.max(8, toPage((drag.w * width / pageWidth) + (event.clientX - drag.originX), width, pageWidth));
        var nextH = Math.max(8, toPage((drag.h * height / pageHeight) + (event.clientY - drag.originY), height, pageHeight));
        if (key === "qr") {
          spec.size = nextW;
          spec.w = nextW;
          spec.h = nextW;
        } else {
          spec.w = nextW;
          spec.h = nextH;
        }
      }
      writeConfig();
      fillInputs();
    });
    box.addEventListener("pointerup", function (event) {
      if (drag && drag.pointer === event.pointerId) drag = null;
    });
    box.addEventListener("pointercancel", function (event) {
      if (drag && drag.pointer === event.pointerId) drag = null;
    });
  });

  artwork.addEventListener("load", function () {
    fillInputs();
    writeConfig();
  });
  window.addEventListener("resize", paint);
  fillInputs();
  writeConfig();
})();
