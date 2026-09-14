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

// Settings: filtering and selecting are two different things, so they are
// two separate rows of controls. The selection actions act on what the
// filters left visible.
const settings = document.getElementById("settings-table");
if (settings) {
  const rows = () => [...settings.tBodies[0].rows];
  const boxes = () => rows().map((row) => row.querySelector('input[type="checkbox"]'));
  const counter = document.getElementById("count");
  const counterBottom = document.getElementById("count-bottom");
  const visible = document.getElementById("visible");
  const text = document.getElementById("filter");
  const kind = document.getElementById("f-kind");
  const state = document.getElementById("f-state");
  const ha = document.getElementById("f-ha");
  const language = document.getElementById("f-lang");

  const matches = (row) => {
    const needle = (text.value || "").toLowerCase();
    if (needle && !row.textContent.toLowerCase().includes(needle)) return false;

    switch (kind.value) {
      case "own":      if (row.dataset.fork === "1") return false; break;
      case "fork":     if (row.dataset.fork !== "1") return false; break;
      case "private":  if (row.dataset.private !== "1") return false; break;
      case "public":   if (row.dataset.private === "1") return false; break;
      case "archived": if (row.dataset.archived !== "1") return false; break;
      case "active":   if (row.dataset.archived === "1") return false; break;
    }

    // "followed" means what is ticked right now, not what was stored
    const ticked = row.querySelector('input[type="checkbox"]').checked;
    if (state.value === "tracked" && !ticked) return false;
    if (state.value === "untracked" && ticked) return false;

    if (ha.value === "yes" && row.dataset.ha !== "1") return false;
    if (ha.value === "no" && row.dataset.ha === "1") return false;

    if (language.value && row.dataset.language !== language.value) return false;
    return true;
  };

  const apply = () => {
    let shown = 0;
    rows().forEach((row) => {
      const ok = matches(row);
      row.hidden = !ok;
      if (ok) shown += 1;
    });
    const all = rows().length;
    const picked = boxes().filter((box) => box.checked).length;
    if (visible) {
      visible.textContent = visible.dataset.template
        .replace("{shown}", shown).replace("{total}", all);
    }
    if (counter) counter.textContent = picked;
    if (counterBottom) counterBottom.textContent = counterBottom.dataset.template
      .replace("{n}", picked);
  };

  [text, kind, state, ha, language].forEach((control) => {
    if (control) control.addEventListener("input", apply);
  });

  document.getElementById("f-reset")?.addEventListener("click", () => {
    text.value = "";
    [kind, state, ha, language].forEach((control) => {
      control.value = "";
      // the widget in front of it listens for this
      control.dispatchEvent(new Event("input", { bubbles: true }));
    });
    apply();
  });

  document.querySelectorAll("[data-select]").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.select;
      rows().forEach((row) => {
        if (row.hidden) return;
        const box = row.querySelector('input[type="checkbox"]');
        if (!box) return;
        if (mode === "check") box.checked = true;
        else if (mode === "uncheck") box.checked = false;
        else if (mode === "invert") box.checked = !box.checked;
      });
      apply();
    });
  });

  settings.addEventListener("change", apply);
  apply();
}

// Native dropdowns cannot be styled once they open — the browser draws that
// list itself. So each <select> keeps working as the source of truth and is
// hidden behind a small widget that looks like the rest of the page.
document.querySelectorAll(".pick select").forEach((select) => {
  const wrap = document.createElement("div");
  wrap.className = "combo";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "combo-button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");

  const list = document.createElement("ul");
  list.className = "combo-list";
  list.setAttribute("role", "listbox");
  list.hidden = true;

  const label = () => {
    button.textContent = select.options[select.selectedIndex]?.textContent ?? "";
    button.classList.toggle("set", select.selectedIndex > 0);
  };

  [...select.options].forEach((option, index) => {
    const item = document.createElement("li");
    item.textContent = option.textContent;
    item.setAttribute("role", "option");
    item.tabIndex = -1;
    item.addEventListener("click", (event) => {
      event.stopPropagation();
      event.preventDefault();
      select.selectedIndex = index;
      list.hidden = true;
      wrap.classList.remove("open");
      button.setAttribute("aria-expanded", "false");
      label();
      select.dispatchEvent(new Event("input", { bubbles: true }));
    });
    list.appendChild(item);
  });

  const mark = () => {
    [...list.children].forEach((item, index) => {
      item.classList.toggle("on", index === select.selectedIndex);
    });
  };

  const close = () => {
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    wrap.classList.remove("open");
  };

  const open = () => {
    document.querySelectorAll(".combo.open").forEach((other) => {
      other.classList.remove("open");
      other.querySelector(".combo-list").hidden = true;
      other.querySelector(".combo-button").setAttribute("aria-expanded", "false");
    });
    mark();
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    wrap.classList.add("open");
  };

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    list.hidden ? open() : close();
  });

  select.addEventListener("input", label);
  document.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });

  select.classList.add("visually-hidden");
  select.parentNode.insertBefore(wrap, select);
  wrap.append(button, list, select);
  label();
});

// Forms that ask before they act.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
