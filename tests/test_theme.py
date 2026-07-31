"""The palette has one source of truth, and this is what enforces it.

A theme pass once updated the application's stylesheet and left
src/config/settings.py alone. The figures kept the old palette and rendered as
lighter panels on the new black background — in the application and on the
published site both — and nothing failed, because nothing was checking. These
tests are the check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stylesheets_match_settings():
    """Both stylesheets are regenerable from COLORS with no diff.

    If this fails, someone hand-edited a generated block or changed COLORS
    without regenerating: run `python tools/gen_theme.py`.
    """
    r = subprocess.run(
        [sys.executable, "tools/gen_theme.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"theme drift:\n{r.stdout}{r.stderr}"


def test_figure_colors_come_from_settings():
    """No module hardcodes a hex colour that the palette should own.

    Voltage-class and loading-band colours are exempt: those encode grid
    operator conventions rather than theme choices — 345 kV is that colour
    because operators expect it, not because a designer picked it.
    """
    from src.config.settings import COLORS

    owned = {v.lower() for k, v in COLORS.items()
             if k in {"bg", "surface", "surface_alt", "accent", "accent_dim", "plot_bg"}}
    retired = {"#070b12", "#0a0e17", "#131a29", "#00c8ff", "#0a7ea4", "#1a2438"}

    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        if path.name in {"settings.py", "power_flow.py"}:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            low = line.lower()
            if low.lstrip().startswith("#"):        # a comment, not code
                continue
            for hexval in retired | owned:
                if f'"{hexval}"' in low:
                    offenders.append(f"{path.relative_to(ROOT)}:{i}: {hexval}")
    assert not offenders, (
        "palette colours hardcoded instead of read from COLORS:\n  "
        + "\n  ".join(offenders))
