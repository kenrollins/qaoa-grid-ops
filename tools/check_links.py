#!/usr/bin/env python
"""Fail the build if any internal link in the generated site 404s.

The footer's "Read the full disclaimer" link was written as the relative href
"about/". mkdocs rewrites relative links in MARKDOWN, but the copyright block is
raw HTML passed through untouched -- so from /hardware/ it resolved to
/hardware/about/ and 404'd on every page of the site except the home page. It
looked correct in the config and in the source, and the only way to see it was
to follow it from a nested page.

Run after `mkdocs build`:  python tools/check_links.py [site_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP = ("http://", "https://", "mailto:", "javascript:", "data:", "//")


def _base_path() -> str:
    """The path GitHub Pages serves this project under, e.g. /qaoa-grid-ops/.

    Root-absolute links in the built site carry this prefix -- correct once
    deployed, but meaningless against a local site/ directory, where they would
    all look broken. Read it from site_url rather than hardcoding, so a rename
    of the repository does not silently turn this checker into noise.
    """
    cfg = (Path(__file__).resolve().parents[1] / "mkdocs.yml").read_text()
    m = re.search(r"^site_url:\s*(\S+)", cfg, re.M)
    if not m:
        return "/"
    path = re.sub(r"^https?://[^/]+", "", m.group(1).strip())
    return path if path.endswith("/") else path + "/"


def main() -> int:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site").resolve()
    if not site.is_dir():
        print(f"no such directory: {site}", file=sys.stderr)
        return 2

    base = _base_path()
    broken: list[str] = []
    pages = 0
    for page in site.rglob("*.html"):
        pages += 1
        for href in re.findall(r'href="([^"]+)"', page.read_text(errors="ignore")):
            href = href.split("#")[0].split("?")[0]
            if not href or href.startswith(SKIP):
                continue
            if href.startswith("/"):
                rel = href[len(base):] if href.startswith(base) else href.lstrip("/")
                target = site / rel
            else:
                target = page.parent / href
            target = target.resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{page.relative_to(site)} -> {href}")

    if broken:
        print(f"{len(broken)} broken internal link(s) across {pages} pages:", file=sys.stderr)
        for b in sorted(set(broken)):
            print(f"  {b}", file=sys.stderr)
        return 1
    print(f"links ok — {pages} pages, no broken internal links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
