#!/usr/bin/env python
"""Generate the palette blocks in both stylesheets from src/config/settings.py.

The application and the published site are styled by two different stylesheets,
and the figures are coloured by a Python dict. Keeping three copies of one
palette in agreement by hand does not work: a theme pass updated the app's CSS,
left the dict alone, and every Plotly figure went on rendering in the previous
palette -- lighter panels floating on a new black background, in the app and on
the site both. Nothing caught it, because nothing was checking.

So COLORS in settings.py is the single source of truth, and this script writes
the derived custom properties into each stylesheet between marker comments.
Everything outside the markers is hand-written and never touched.

  python tools/gen_theme.py            # write
  python tools/gen_theme.py --check    # exit 1 if either file is stale

tests/test_theme.py runs --check, so drift fails CI rather than shipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP_CSS = ROOT / "src" / "ui" / "style.css"
SITE_CSS = ROOT / "site_src" / "stylesheets" / "extra.css"

BEGIN = "/* >>> generated from src/config/settings.py — do not edit by hand */"

# Material derives its dark-theme foreground ramp from ONE colour at four
# alphas. Body text is 0.82, not 1.0 — the translucency is what keeps prose off
# a dark background from glaring. Overriding the top of the ramp with an opaque
# colour made the site brighter than stock Material, and left the bottom two
# steps resolving against a hue variable that was never set.
FG_ALPHAS = {"": 0.82, "--light": 0.56, "--lighter": 0.32, "--lightest": 0.12}


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
END = "/* <<< end generated */"


def _app_block(c: dict[str, str]) -> str:
    """The application's own custom properties.

    Font tokens are deliberately not generated: they are not colours and do not
    belong to the palette, so they stay hand-written below this block.
    """
    return "\n".join([
        f"  --bg: {c['bg']};",
        f"  --surface: {c['surface']};",
        f"  --surface-alt: {c['surface_alt']};",
        f"  --border: {c['border']};",
        f"  --accent: {c['accent']};",
        f"  --accent-dim: {c['accent_dim']};",
        f"  --text: {c['text']};",
        f"  --text-dim: {c['text_dim']};",
        f"  --ok: {c['ok']};",
        f"  --warn: {c['warn']};",
        f"  --crit: {c['crit']};",
        f"  --island-a: {c['island_a']};",
        f"  --island-b: {c['island_b']};",
        f"  --line: {c['line']};",
        f"  --plot-bg: {c['plot_bg']};",
    ])


def _site_block(c: dict[str, str]) -> str:
    """Material's custom properties, mapped from the same palette.

    Material paints the whole header with the PRIMARY colour, so primary is the
    surface rather than the accent -- pointing it at the accent produces a large
    bright slab, which is the opposite of the app, where the accent appears only
    as a hairline and a glow.
    """
    r, g, b = _rgb(c["text"])
    grid = c["surface_alt"]
    stripe = (f"linear-gradient({{deg}}deg, transparent 0%, transparent calc(100% - 1px), "
              f"{grid} calc(100% - 1px), {grid} 100%)")
    return "\n".join([
        ":root {",
        f"  --md-primary-fg-color:        {c['surface']};",
        f"  --md-primary-fg-color--dark:  {c['bg']};",
        f"  --md-primary-bg-color:        {c['text']};",
        f"  --md-primary-bg-color--light: {c['text_dim']};",
        f"  --md-accent-fg-color:         {c['accent']};",
        "}",
        '[data-md-color-scheme="slate"] {',
        f"  --md-default-bg-color:        {c['bg']};",
        f"  --md-code-bg-color:           {c['surface']};",
        *[f"  --md-default-fg-color{suffix}: rgba({r}, {g}, {b}, {a});"
          for suffix, a in FG_ALPHAS.items()],
        f"  --md-typeset-a-color:         {c['accent']};",
        f"  --md-footer-bg-color:         {c['surface']};",
        f"  --md-footer-bg-color--dark:   {c['bg']};",
        "}",
        "/* Header/content separation. The page is pure black and the header is",
        "   one step above it, which on its own is nearly invisible -- so the",
        "   header also carries the application's grid signature, the accent",
        "   hairline, and its glow. Same device as the app, same reason. */",
        ".md-header, .md-tabs {",
        "  background:",
        f"    {stripe.format(deg=90)},",
        f"    {stripe.format(deg=0)},",
        f"    {c['surface']};",
        "  background-size: 24px 24px;",
        "}",
        ".md-header {",
        f"  border-bottom: 2px solid {c['accent']};",
        "  box-shadow: 0 6px 28px -6px rgba(0,153,204,.45);",
        "}",
        f".md-tabs__link--active, .md-tabs__link:hover {{ color: {c['accent']}; opacity: 1; }}",
        ".md-search__form { background: rgba(255,255,255,.06); }",
        ".md-search__form:hover { background: rgba(0,153,204,.16); }",
    ])


def _splice(path: Path, block: str) -> str:
    """Return the file with the generated region replaced. Fails loudly if the
    markers are missing, rather than silently appending or overwriting."""
    text = path.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{path}: missing generated markers — add {BEGIN} … {END}")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return f"{head}{BEGIN}\n{block}\n{END}{tail}"


def main() -> int:
    from src.config.settings import COLORS

    check = "--check" in sys.argv
    stale = []
    for path, block in ((APP_CSS, _app_block(COLORS)), (SITE_CSS, _site_block(COLORS))):
        want = _splice(path, block)
        if path.read_text() == want:
            continue
        if check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(want)
            print(f"  wrote  {path.relative_to(ROOT)}")

    if stale:
        names = ", ".join(str(p) for p in stale)
        print(f"stale: {names}\nrun: python tools/gen_theme.py", file=sys.stderr)
        return 1
    if check:
        print("theme in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
