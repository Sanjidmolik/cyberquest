(function () {
  "use strict";
  var node = document.getElementById("mission-chart-data");
  if (!node) return;
  var data = {};
  try { data = JSON.parse(node.textContent || "{}"); } catch (err) { data = {}; }

  function empty(host, text) {
    host.textContent = text;
    host.classList.add("ma-empty");
  }

  function svgEl(name, attrs) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs).forEach(function (key) { el.setAttribute(key, attrs[key]); });
    return el;
  }

  function barChart(host, rows, valueKey, labelKey) {
    var values = rows.map(function (row) { return row[valueKey] || 0; });
    var max = Math.max.apply(null, values.concat([1]));
    var svg = svgEl("svg", { viewBox: "0 0 360 200", role: "img" });
    rows.forEach(function (row, index) {
      var height = ((row[valueKey] || 0) / max) * 140;
      var x = 20 + index * 68;
      svg.appendChild(svgEl("rect", {
        x: x, y: 160 - height, width: 36, height: height, fill: "#c9964e",
      }));
      var label = svgEl("text", { x: x, y: 178 });
      label.textContent = (row[labelKey] || "").slice(0, 8);
      svg.appendChild(label);
      var value = svgEl("text", { x: x, y: 152 - height });
      value.textContent = row[valueKey] == null ? "—" : String(row[valueKey]);
      svg.appendChild(value);
    });
    host.appendChild(svg);
  }

  var timeHost = document.getElementById("chart-time");
  var timed = (data.by_mission || []).filter(function (row) { return row.avg_time != null; });
  if (timeHost) {
    if (!timed.length) empty(timeHost, "No measured completion times in this filter.");
    else barChart(timeHost, data.by_mission.map(function (row) {
      return { name: row.name, avg_time: row.avg_time || 0 };
    }), "avg_time", "name");
  }

  var outcomeHost = document.getElementById("chart-outcomes");
  if (outcomeHost) {
    var anyOutcome = (data.by_mission || []).some(function (row) { return row.completed || row.timed_out; });
    if (!anyOutcome) empty(outcomeHost, "No finished attempts in this filter.");
    else {
      var svg = svgEl("svg", { viewBox: "0 0 360 200" });
      var max = 1;
      data.by_mission.forEach(function (row) { max = Math.max(max, row.completed, row.timed_out); });
      data.by_mission.forEach(function (row, index) {
        var x = 16 + index * 68;
        var done = (row.completed / max) * 130;
        var out = (row.timed_out / max) * 130;
        svg.appendChild(svgEl("rect", { x: x, y: 150 - done, width: 16, height: done, fill: "#7dcea0" }));
        svg.appendChild(svgEl("rect", { x: x + 20, y: 150 - out, width: 16, height: out, fill: "#e7b7b7" }));
        var label = svgEl("text", { x: x, y: 172 });
        label.textContent = row.name.slice(0, 8);
        svg.appendChild(label);
      });
      outcomeHost.appendChild(svg);
    }
  }

  var scatterHost = document.getElementById("chart-scatter");
  if (scatterHost) {
    if (!(data.scatter || []).length) empty(scatterHost, "No timed attempts to plot.");
    else {
      var svg = svgEl("svg", { viewBox: "0 0 360 200" });
      var maxX = Math.max.apply(null, data.scatter.map(function (point) { return point.x; }).concat([60]));
      svg.appendChild(svgEl("line", { x1: 30, y1: 20, x2: 30, y2: 170, stroke: "#9aabbb" }));
      svg.appendChild(svgEl("line", { x1: 30, y1: 170, x2: 340, y2: 170, stroke: "#9aabbb" }));
      var yThreshold = 170 - (data.threshold / 100) * 150;
      var xFast = 30 + (data.fast_mark / maxX) * 300;
      svg.appendChild(svgEl("line", { x1: 30, y1: yThreshold, x2: 340, y2: yThreshold, stroke: "#c9964e", "stroke-dasharray": "4 3" }));
      svg.appendChild(svgEl("line", { x1: xFast, y1: 20, x2: xFast, y2: 170, stroke: "#9fd0ff", "stroke-dasharray": "4 3" }));
      data.scatter.forEach(function (point) {
        var x = 30 + (point.x / maxX) * 300;
        var y = 170 - (point.y / 100) * 150;
        var fill = point.high && point.fast ? "#1f9d62" : point.fast ? "#c5363a" : point.high ? "#2f6fce" : "#8a7a68";
        var dot = svgEl("circle", { cx: x, cy: y, r: 4, fill: fill });
        var title = svgEl("title", {});
        title.textContent = point.learner + " · " + point.mission + " · " + point.x + "s · " + point.y + "%";
        dot.appendChild(title);
        svg.appendChild(dot);
      });
      scatterHost.appendChild(svg);
    }
  }

  var activityHost = document.getElementById("chart-activity");
  if (activityHost) {
    if (!(data.activity || []).length) empty(activityHost, "No completed attempts in this range.");
    else barChart(activityHost, data.activity.slice(-12).map(function (row) {
      return { name: row.label.slice(5), count: row.count };
    }), "count", "name");
  }

  var leaderHost = document.getElementById("chart-leaders");
  if (leaderHost) {
    if (!(data.leaders || []).length) empty(leaderHost, "No qualifying learners in this filter.");
    else barChart(leaderHost, data.leaders.map(function (row) {
      return { name: row.learner, seconds: row.seconds };
    }), "seconds", "name");
  }
})();
