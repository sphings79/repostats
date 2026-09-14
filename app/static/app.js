// Hover read-outs for the charts and the small helpers on the settings page.

document.querySelectorAll("[data-tooltip]").forEach((wrap) => {
  const tip = wrap.querySelector(".tooltip");
  const cursor = wrap.querySelector(".cursor");
  if (!tip) return;

  wrap.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("mouseenter", () => {
      const day = hit.dataset.day || "";
      const text = hit.dataset.text || "";
      const [y, m, d] = day.split("-");
      tip.innerHTML = `<b>${d}.${m}.${y}</b><br>${text}`;
      tip.hidden = false;

      const box = wrap.getBoundingClientRect();
      const hitBox = hit.getBoundingClientRect();
      const x = hitBox.left - box.left + hitBox.width / 2;
      tip.style.left = Math.min(Math.max(x - tip.offsetWidth / 2, 4),
                                box.width - tip.offsetWidth - 4) + "px";
      tip.style.top = "8px";

      if (cursor) {
        const svg = wrap.querySelector("svg");
        const scale = svg.viewBox.baseVal.width / svg.clientWidth;
        const vx = (hitBox.left - box.left + hitBox.width / 2) * scale;
        cursor.setAttribute("x1", vx);
        cursor.setAttribute("x2", vx);
        cursor.setAttribute("y1", 14);
        cursor.setAttribute("y2", svg.viewBox.baseVal.height - 26);
        cursor.setAttribute("opacity", "0.6");
      }
    });
  });

  wrap.addEventListener("mouseleave", () => {
    tip.hidden = true;
    if (cursor) cursor.setAttribute("opacity", "0");
  });
});

// Sortable overview table.
const table = document.getElementById("repo-table");
if (table) {
  table.querySelectorAll("th[data-sort]").forEach((th, index) => {
    th.addEventListener("click", () => {
      const body = table.tBodies[0];
      const rows = [...body.rows];
      const numeric = th.dataset.sort === "num";
      const asc = th.classList.contains("sorted") && !th.classList.contains("asc");

      table.querySelectorAll("th").forEach((other) => other.classList.remove("sorted", "asc"));
      th.classList.add("sorted");
      if (asc) th.classList.add("asc");

      rows.sort((a, b) => {
        const left = a.cells[index].textContent.trim();
        const right = b.cells[index].textContent.trim();
        if (numeric) {
          const l = parseInt(left.replace(/\./g, ""), 10) || 0;
          const r = parseInt(right.replace(/\./g, ""), 10) || 0;
          return asc ? l - r : r - l;
        }
        return asc ? left.localeCompare(right, "de") : right.localeCompare(left, "de");
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
}

// Settings: filter, bulk select, live count.
const settings = document.getElementById("settings-table");
if (settings) {
  const boxes = () => [...settings.querySelectorAll('input[type="checkbox"]')];
  const counter = document.getElementById("count");
  const update = () => {
    if (counter) counter.textContent = boxes().filter((b) => b.checked).length;
  };

  const filter = document.getElementById("filter");
  if (filter) {
    filter.addEventListener("input", () => {
      const needle = filter.value.toLowerCase();
      [...settings.tBodies[0].rows].forEach((row) => {
        row.hidden = needle && !row.textContent.toLowerCase().includes(needle);
      });
    });
  }

  document.querySelectorAll("[data-select]").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.select;
      [...settings.tBodies[0].rows].forEach((row) => {
        if (row.hidden) return;
        const box = row.querySelector('input[type="checkbox"]');
        if (!box) return;
        if (mode === "all") box.checked = true;
        else if (mode === "none") box.checked = false;
        else if (mode === "own") box.checked = row.dataset.fork !== "1";
      });
      update();
    });
  });

  settings.addEventListener("change", update);
  update();
}
