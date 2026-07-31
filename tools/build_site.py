#!/usr/bin/env python
"""Generate the static site's figures and copy the notes in.

Two things this does that a hand-written site could not:

  1. **The figures are produced by the demo's own engine**, exported to
     standalone interactive HTML at build time. The published charts are the
     same computation the live application runs, not screenshots of it.
  2. **The technical notes are copied, not rewritten.** `docs/journal/notes/`
     stays the single copy; drift between the repository and the site is
     impossible by construction.

What the site cannot mirror is anything reading live GB10 state — a published
page has no backend. Those figures carry the measurement date instead, which is
what the notes already do.

Run:  python tools/build_site.py   (then `mkdocs build`)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SRC = ROOT / "site_src"
FIGS = SRC / "figures"
NOTES_SRC = ROOT / "docs" / "journal" / "notes"
NOTES_DST = SRC / "notes"
PLOTLY_DST = SRC / "js" / "plotly.min.js"

# Fragments never carry the library. mkdocs.yml loads plotly once per page via
# extra_javascript; baking it into "the first" fragment left every page that did
# not happen to contain that figure rendering its charts blank.
PLOTLY_MODE = False

# mkdocs emits extra_javascript at the end of <body>, so the library loads AFTER
# these inline scripts have already run and Plotly is undefined at that moment.
# Every figure drew an empty box. Waiting for DOMContentLoaded is not enough on
# its own either -- if the browser has the script cached the event may already
# have fired -- so check for the library first and fall back to the event.
GATE_OPEN = """<script>(function(){function draw(){"""
GATE_SHUT = """}
if (window.Plotly) { draw(); }
else { document.addEventListener("DOMContentLoaded", draw); }
})();</script>"""


def _wrap_title(fig, limit: int = 62) -> None:
    """Break long titles onto a second line.

    These titles were written for the application, whose plot area is the full
    browser width. The site puts the same figures in a column between a nav and
    a table of contents, where plotly silently clips the overflow -- one title
    lost its provenance mid-word ("...cuS").
    """
    title = getattr(fig.layout.title, "text", None)
    if not title or len(title) <= limit or "<br>" in title:
        return
    cut = title.rfind(" ", 0, limit)
    if cut > 0:
        fig.update_layout(title_text=title[:cut] + "<br>" + title[cut + 1:])
        fig.update_layout(margin=dict(t=64))


def _write_fragment(fig, name: str) -> None:
    """Export one figure as an embeddable HTML fragment."""
    FIGS.mkdir(parents=True, exist_ok=True)
    html = fig.to_html(
        include_plotlyjs=PLOTLY_MODE,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
        default_height="480px",
    )
    # Plotly emits the whole fragment on one line, padded with runs of spaces:
    #   <div ...>        <div id=...></div>            <script>...
    # md_in_html ends the raw-HTML block at that inner </div>, so the REST of
    # the line -- twelve spaces, then <script> -- became an indented code block.
    # Markdown escaped the script and printed it as text instead of the browser
    # executing it, and every figure on the site rendered as an empty box.
    #
    # Putting each tag on its own line at column zero removes both the mid-line
    # start and any leading indentation. Nothing here depends on whitespace:
    # plotly escapes < and > inside the JSON payload as \u003c / \u003e, so no
    # tag boundary can fall inside the data.
    html = re.sub(r">\s+<", ">\n<", html)
    html = "\n".join(line.lstrip() for line in html.splitlines())

    head, _, rest = html.partition("<script>")
    body, _, tail = rest.rpartition("</script>")
    if not body:                       # layout changed upstream -- do not fail silently
        raise RuntimeError(f"{name}: no <script> block to gate; check plotly version")
    (FIGS / f"{name}.html").write_text(head + GATE_OPEN + body + GATE_SHUT + tail)
    print(f"  figure  {name}")


def build_figures() -> None:
    from src.config.settings import GridSpec
    from src.simulation import power_flow as pf
    from src.simulation.grid_model import apply_fault, build_grid
    from src.ui import control_room as cr
    from src.ui.views.learn import (
        interference_figure, landscape_figure, noise_memory_figure,
        tradeoff_figure, trajectory_convergence_figure,
    )
    from src.ui.views.limits import (
        crossover_figure, memory_wall_figure, scaling_measured_figure,
    )

    n, seed = 10, 7
    spec = GridSpec(n_nodes=12, seed=seed)
    grid = pf.calibrate_ratings(build_grid(spec))
    line = pf.worst_contingency(grid)
    faulted = apply_fault(grid, [line] if line else [])

    jobs = [
        ("grid-normal", cr.one_line_diagram(grid, pf.solve(grid), height=620)),
        ("grid-faulted", cr.one_line_diagram(faulted, pf.solve(faulted), height=620)),
        ("interference", interference_figure(n, seed, 2)),
        ("landscape", landscape_figure(n, seed)),
        ("tradeoff", tradeoff_figure(n, seed)),
        ("memory-wall", memory_wall_figure()),
        ("crossover", crossover_figure()),
        ("noise-memory", noise_memory_figure()),
        ("trajectory-convergence", trajectory_convergence_figure(8, seed, 3.0, 400)),
        ("scaling-measured", scaling_measured_figure()),
    ]
    for name, fig in jobs:
        fig.update_layout(margin=dict(l=55, r=25, t=48, b=45))
        _wrap_title(fig)
        _write_fragment(fig, name)

    # The loading-band key belongs with the diagrams and is pure HTML.
    (FIGS / "loading-key.html").write_text(cr.loading_key(pf.solve(faulted)))
    print("  figure  loading-key")


def copy_plotly() -> None:
    """Vendor plotly.js so the published site depends on no third-party host.

    Taken from the installed plotly package rather than the application's
    static/ copy, which is not in the repository -- CI checked out the source,
    found no static/plotly.min.js and failed the build. Sourcing it from the
    package also guarantees the library is the same version as the one that
    generated these figures.
    """
    import plotly

    src = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    PLOTLY_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, PLOTLY_DST)
    print(f"  vendor  plotly.min.js ({src.stat().st_size // 1024} KB) from {plotly.__version__}")


def copy_notes() -> None:
    """Copy the technical notes verbatim; they are already public-ready."""
    NOTES_DST.mkdir(parents=True, exist_ok=True)
    for f in sorted(NOTES_SRC.glob("*.md")):
        dst = NOTES_DST / ("index.md" if f.name == "README.md" else f.name)
        text = f.read_text()
        # mkdocs renders frontmatter as page metadata; the title is already the
        # first heading, so strip the block rather than show it as YAML.
        if text.startswith("---"):
            _, _, text = text.split("---", 2)
            text = text.lstrip()
        dst.write_text(text)
        print(f"  note    {dst.name}")


def main() -> None:
    print("building site sources")
    # Regenerate the palette first: the stylesheets and the figures are both
    # derived from COLORS, and a site built from a stale stylesheet is exactly
    # the failure this pipeline exists to prevent.
    subprocess.run([sys.executable, str(ROOT / "tools" / "gen_theme.py")], check=True)
    copy_plotly()
    copy_notes()
    build_figures()
    print("done — now run: mkdocs build")


if __name__ == "__main__":
    main()
