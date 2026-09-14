"""Charts, drawn as SVG on the server.

No charting library and no build step: the pages render on their own, work
offline and stay legible when the browser blocks scripts. A small amount of
JavaScript only adds hover read-outs on top of what is already drawn.
"""
from datetime import date, datetime, timedelta
from html import escape

from .i18n import day_label, translator


def _points(rows) -> list[tuple[str, float]]:
    return [(r["day"], float(r["value"] or 0)) for r in rows]


def _fill_gaps(points: list[tuple[str, float]], days: int,
               carry: bool = False) -> list[tuple[str, float]]:
    """Give every day in the window a value.

    Traffic has genuine zero days, so a missing day means "nobody came" and
    becomes 0. Counters like stars keep their last value instead, because a
    day without a collection run does not mean the stars went away.
    """
    known = dict(points)
    today = date.today()
    out: list[tuple[str, float]] = []
    running = 0.0
    first = True
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        if day in known:
            running = known[day]
            first = False
            out.append((day, running))
        elif carry and not first:
            out.append((day, running))
        else:
            out.append((day, 0.0 if not carry else running))
    return out


def sparkline(rows, width: int = 132, height: int = 34, carry: bool = False,
              days: int = 30, accent: str = "var(--accent)") -> str:
    """A small trend line for a KPI tile."""
    series = _fill_gaps(_points(rows), days, carry)
    values = [v for _d, v in series]
    if not values or max(values) == min(values) == 0:
        return (f'<svg class="spark" viewBox="0 0 {width} {height}" '
                f'preserveAspectRatio="none" aria-hidden="true">'
                f'<line x1="0" y1="{height - 2}" x2="{width}" y2="{height - 2}" '
                f'stroke="var(--line)" stroke-width="1"/></svg>')

    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / max(len(values) - 1, 1)
    pad = 3

    def y(value: float) -> float:
        return height - pad - (value - low) / span * (height - 2 * pad)

    line = " ".join(f"{i * step:.1f},{y(v):.1f}" for i, v in enumerate(values))
    area = f"0,{height} {line} {width},{height}"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'aria-hidden="true">'
        f'<polygon points="{area}" fill="{accent}" fill-opacity="0.12"/>'
        f'<polyline points="{line}" fill="none" stroke="{accent}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def area_chart(series: list[dict], days: int = 90, height: int = 220,
               width: int = 960, lang: str = "de") -> str:
    """A larger chart with a hover read-out, for one or two series."""
    prepared = []
    for entry in series:
        points = _fill_gaps(_points(entry["rows"]), days, entry.get("carry", False))
        prepared.append({**entry, "points": points})

    all_values = [v for entry in prepared for _d, v in entry["points"]]
    if not all_values:
        return f'<p class="empty">{translator(lang)("chart.empty")}</p>'

    high = max(all_values) or 1
    low = min(min(all_values), 0)
    span = (high - low) or 1
    left, right, top, bottom = 46, 12, 14, 26
    plot_w = width - left - right
    plot_h = height - top - bottom
    count = max(len(prepared[0]["points"]), 1)
    step = plot_w / max(count - 1, 1)

    def x(i: int) -> float:
        return left + i * step

    def y(value: float) -> float:
        return top + plot_h - (value - low) / span * plot_h

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']

    # horizontal guides with value labels
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        value = low + span * fraction
        py = y(value)
        parts.append(f'<line x1="{left}" y1="{py:.1f}" x2="{width - right}" y2="{py:.1f}" '
                     f'stroke="var(--line)" stroke-width="1" stroke-opacity="0.6"/>')
        parts.append(f'<text x="{left - 8}" y="{py + 4:.1f}" class="axis" '
                     f'text-anchor="end">{_short(value)}</text>')

    for index, entry in enumerate(prepared):
        colour = entry.get("colour", "var(--accent)")
        pts = entry["points"]
        line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_d, v) in enumerate(pts))
        area = f"{left},{y(low):.1f} {line} {width - right},{y(low):.1f}"
        parts.append(f'<polygon points="{area}" fill="{colour}" fill-opacity="0.10"/>')
        parts.append(f'<polyline points="{line}" fill="none" stroke="{colour}" '
                     f'stroke-width="2" stroke-linejoin="round"/>')

    # date labels: first, middle, last
    pts = prepared[0]["points"]
    for i in (0, count // 2, count - 1):
        if 0 <= i < len(pts):
            anchor = "start" if i == 0 else ("end" if i == count - 1 else "middle")
            parts.append(f'<text x="{x(i):.1f}" y="{height - 8}" class="axis" '
                         f'text-anchor="{anchor}">{day_label(pts[i][0], lang)}</text>')

    # one hover column per day, read by the tooltip script
    payload = []
    for i, (day, _v) in enumerate(pts):
        values = [f'{escape(e["label"])}: {int(e["points"][i][1])}' for e in prepared]
        payload.append((x(i), day, " · ".join(values)))
    for px, day, text in payload:
        parts.append(
            f'<rect class="hit" x="{px - step / 2:.1f}" y="{top}" width="{step:.1f}" '
            f'height="{plot_h}" fill="transparent" data-day="{day}" '
            f'data-text="{escape(text)}"/>')
    parts.append('<line class="cursor" x1="0" y1="0" x2="0" y2="0" stroke="var(--muted)" '
                 'stroke-width="1" stroke-dasharray="3 3" opacity="0"/>')
    parts.append("</svg>")

    legend = " ".join(
        f'<span class="key"><i style="background:{e.get("colour", "var(--accent)")}"></i>'
        f'{escape(e["label"])}</span>' for e in prepared)
    return (f'<div class="chart-wrap" data-tooltip>{"".join(parts)}'
            f'<div class="tooltip" hidden></div></div>'
            f'<div class="legend">{legend}</div>')


def bars(rows, label_key: str, value_key: str, limit: int = 10,
         lang: str = "de") -> str:
    """A horizontal bar list, used for referrers and popular paths."""
    rows = list(rows)[:limit]
    if not rows:
        return f'<p class="empty">{translator(lang)("bars.empty")}</p>'
    high = max(r[value_key] for r in rows) or 1
    out = ['<ul class="bars">']
    for row in rows:
        share = row[value_key] / high * 100
        out.append(
            f'<li><span class="bar-label" title="{escape(str(row[label_key]))}">'
            f'{escape(str(row[label_key]))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{share:.1f}%"></span></span>'
            f'<span class="bar-value">{_group(row[value_key], lang)}</span></li>')
    out.append("</ul>")
    return "".join(out)


def _group(value: int, lang: str) -> str:
    text = f"{int(value):,}"
    return text.replace(",", ".") if lang == "de" else text


def _short(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k".replace(".0k", "k")
    return f"{value:.0f}"

