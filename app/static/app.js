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

// The small "i" on a KPI tile opens its explanation. The tile clips its own
// content, so it also has to be told to let the box out while it is open.
const closeHints = (keep) => {
  document.querySelectorAll(".kpi.open").forEach((kpi) => {
    if (kpi === keep) return;
    kpi.classList.remove("open");
    kpi.querySelector(".hint-box").hidden = true;
    kpi.querySelector(".info").setAttribute("aria-expanded", "false");
  });
};

document.querySelectorAll(".kpi .info").forEach((button) => {
  const kpi = button.closest(".kpi");
  const box = kpi.querySelector(".hint-box");
  if (!box) return;

  button.addEventListener("click", (event) => {
    // the whole tile can be a link, so the click must not travel further
    event.stopPropagation();
    event.preventDefault();
    const open = kpi.classList.contains("open");
    closeHints(kpi);
    kpi.classList.toggle("open", !open);
    box.hidden = open;
    button.setAttribute("aria-expanded", String(!open));
  });
});

document.addEventListener("click", (event) => {
  // a click inside the box itself leaves it open
  if (!event.target.closest(".hint-box")) closeHints();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeHints();
});

// Sortable tables. A cell may carry the exact value in data-v, because its
// text can hold more than the number (a small change next to it).
document.querySelectorAll("table.sortable").forEach((table) => {
  table.querySelectorAll("th[data-sort]").forEach((th) => {
    const index = th.cellIndex;
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
          const value = (cell) => cell.dataset.v !== undefined
            ? parseFloat(cell.dataset.v) || 0
            : parseInt(cell.textContent.trim().replace(/\./g, ""), 10) || 0;
          const l = value(a.cells[index]);
          const r = value(b.cells[index]);
          return asc ? l - r : r - l;
        }
        return asc ? left.localeCompare(right, "de") : right.localeCompare(left, "de");
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
});

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
  const topic = document.getElementById("f-topic");
  const pageSize = document.getElementById("page-size");
  const pageInfo = document.getElementById("page-info");
  const prev = document.getElementById("page-prev");
  const next = document.getElementById("page-next");
  let page = 1;

  // the page size is remembered per browser; the page itself is not
  try {
    const saved = window.localStorage.getItem("repostats.pageSize");
    if (saved !== null && [...pageSize.options].some((o) => o.value === saved)) pageSize.value = saved;
  } catch (_) { /* private mode: the default stays */ }

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
    if (topic.value && !row.dataset.topics.includes("," + topic.value + ",")) return false;
    return true;
  };

  // What the filters let through is one thing, what fits on the page another:
  // the selection actions below work on everything the filters let through.
  const apply = () => {
    const matched = [];
    rows().forEach((row) => {
      const ok = matches(row);
      row.dataset.match = ok ? "1" : "0";
      row.hidden = true;
      if (ok) matched.push(row);
    });
    const shown = matched.length;
    const size = parseInt(pageSize.value, 10) || 0;
    const pages = size ? Math.max(1, Math.ceil(shown / size)) : 1;
    page = Math.min(Math.max(page, 1), pages);
    const start = size ? (page - 1) * size : 0;
    const end = size ? start + size : shown;
    matched.slice(start, end).forEach((row) => { row.hidden = false; });
    if (pageInfo) {
      pageInfo.textContent = pageInfo.dataset.template
        .replace("{a}", shown ? start + 1 : 0).replace("{b}", Math.min(end, shown))
        .replace("{n}", shown).replace("{page}", page).replace("{pages}", pages);
    }
    if (prev) prev.disabled = page <= 1;
    if (next) next.disabled = page >= pages;
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

  // a new filter starts on the first page again
  [text, kind, state, ha, language, topic].forEach((control) => {
    if (control) control.addEventListener("input", () => { page = 1; apply(); });
  });

  pageSize.addEventListener("input", () => {
    page = 1;
    try { window.localStorage.setItem("repostats.pageSize", pageSize.value); } catch (_) { /* fine */ }
    apply();
  });
  prev.addEventListener("click", () => { page -= 1; apply(); });
  next.addEventListener("click", () => { page += 1; apply(); });

  document.getElementById("f-reset")?.addEventListener("click", () => {
    text.value = "";
    [kind, state, ha, language, topic].forEach((control) => {
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
        if (row.dataset.match !== "1") return;
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

  // Long lists (topics) get a search field on top of the open list.
  let find = null;
  let none = null;
  if (select.dataset.search !== undefined) {
    find = document.createElement("input");
    find.type = "search";
    find.className = "combo-find";
    find.autocomplete = "off";
    find.placeholder = document.documentElement.lang === "de" ? "Suchen …" : "Search …";
    none = document.createElement("li");
    none.className = "combo-none";
    none.textContent = document.documentElement.lang === "de" ? "Kein Treffer" : "No match";
    none.hidden = true;
  }

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
  if (find) list.prepend(find);
  if (none) list.appendChild(none);

  const items = () => [...list.querySelectorAll("li[role=option]")];
  const shown = () => items().filter((item) => !item.hidden);

  const narrow = () => {
    const needle = find.value.trim().toLowerCase();
    items().forEach((item, index) => {
      // the first entry is the "any" choice and goes away while searching
      item.hidden = needle !== "" && (index === 0 ||
        !item.textContent.toLowerCase().includes(needle));
    });
    none.hidden = needle === "" || shown().length > 0;
  };

  const mark = () => {
    items().forEach((item, index) => {
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
    if (find) {
      find.value = "";
      narrow();
      find.focus();
    }
  };

  if (find) {
    // clicks and keys inside the search field must not close the list
    find.addEventListener("click", (event) => event.stopPropagation());
    find.addEventListener("input", (event) => {
      event.stopPropagation();
      narrow();
    });
    find.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        shown()[0]?.click();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        shown()[0]?.focus();
      }
    });
    list.addEventListener("keydown", (event) => {
      const visible = shown();
      const at = visible.indexOf(document.activeElement);
      if (event.key === "ArrowDown" && at >= 0) {
        event.preventDefault();
        visible[Math.min(at + 1, visible.length - 1)].focus();
      } else if (event.key === "ArrowUp" && at >= 0) {
        event.preventDefault();
        (at === 0 ? find : visible[at - 1]).focus();
      } else if (event.key === "Enter" && at >= 0) {
        event.preventDefault();
        visible[at].click();
      }
    });
  }

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

// A dropdown that reloads the page with its value as a query parameter,
// leaving the other parameters (repository, bots …) as they are.
document.querySelectorAll("select[data-nav]").forEach((select) => {
  select.addEventListener("input", () => {
    const query = new URLSearchParams(window.location.search);
    if (select.value) query.set(select.dataset.nav, select.value);
    else query.delete(select.dataset.nav);
    window.location.search = query.toString();
  });
});

// A dropdown that adds what is picked to a list of removable chips; each chip
// carries a hidden field, so the surrounding form submits the list.
document.querySelectorAll("select[data-chips]").forEach((select) => {
  const box = document.querySelector(select.dataset.chips);
  if (!box) return;
  const name = "hidden_topics";

  const wire = (chip) => {
    chip.querySelector("button")?.addEventListener("click", () => chip.remove());
  };
  box.querySelectorAll(".chip").forEach(wire);

  select.addEventListener("input", () => {
    const topic = select.value;
    if (!topic) return;
    const have = [...box.querySelectorAll("input")].some((input) => input.value === topic);
    if (!have) {
      const chip = document.createElement("span");
      chip.className = "chip";
      const field = document.createElement("input");
      field.type = "hidden";
      field.name = name;
      field.value = topic;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", box.dataset.remove || "Remove");
      chip.append(field, topic, remove);
      wire(chip);
      box.appendChild(chip);
    }
    // back to the prompt, ready for the next one
    select.selectedIndex = 0;
    select.dispatchEvent(new Event("input"));
  });
});

// Forms that ask before they act.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// Burger menu on small screens.
(() => {
  const burger = document.querySelector(".burger");
  const nav = document.getElementById("main-nav");
  if (!burger || !nav) return;
  const set = (open) => {
    nav.classList.toggle("open", open);
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  };
  burger.addEventListener("click", (event) => {
    event.stopPropagation();
    set(!nav.classList.contains("open"));
  });
  document.addEventListener("click", (event) => {
    if (!nav.contains(event.target)) set(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") set(false);
  });
})();
