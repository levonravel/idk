#!/usr/bin/env python3
"""Stamp local image URLs in the site's HTML with a hash of the image's bytes.

Turns  src="img/spicy-pickles.jpg"
into   src="img/spicy-pickles.jpg?v=1a2b3c4d"

The hash is derived from the file contents, so replacing a photo (even with the
same filename) produces a new URL and every visitor's browser fetches the new
image immediately instead of serving a stale copy out of its cache.

Re-running with no image changes rewrites nothing, so it is safe to run on
every push.

Usage:  python tools/stamp-cache-bust.py [--check]
        --check  exit 1 if any file would change, without writing
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_GLOBS = ("*.html",)
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "svg", "avif", "ico")

# src="path.jpg" / href="path.png" / url(path.webp), with an optional existing ?v=...
ATTR_RE = re.compile(
    r'(?P<attr>\b(?:src|href|poster|content)\s*=\s*")'
    r'(?P<path>[^"\s?#>]+\.(?:' + "|".join(IMAGE_EXTS) + r'))'
    r'(?P<query>\?v=[0-9a-f]+)?'
    r'(?P<end>")',
    re.IGNORECASE,
)
URL_RE = re.compile(
    r'(?P<attr>url\(\s*(?P<quote>["\']?))'
    r'(?P<path>[^"\'\s?#)]+\.(?:' + "|".join(IMAGE_EXTS) + r'))'
    r'(?P<query>\?v=[0-9a-f]+)?'
    r'(?P<end>(?P=quote)\s*\))',
    re.IGNORECASE,
)

_hash_cache: dict[Path, str] = {}


def short_hash(path: Path) -> str:
    if path not in _hash_cache:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _hash_cache[path] = digest[:8]
    return _hash_cache[path]


def resolve(html_file: Path, url_path: str) -> Path | None:
    """Map a URL in an HTML file to a file on disk, or None if it isn't local."""
    if "//" in url_path or url_path.startswith(("data:", "mailto:")):
        return None
    candidate = (ROOT / url_path.lstrip("/")) if url_path.startswith("/") \
        else (html_file.parent / url_path)
    try:
        candidate = candidate.resolve()
        candidate.relative_to(ROOT)  # refuse to reach outside the repo
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def stamp(html_file: Path) -> tuple[str, int]:
    # newline="" so existing CRLF/LF line endings survive the round trip untouched
    with open(html_file, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        target = resolve(html_file, match.group("path"))
        if target is None:
            return match.group(0)
        stamped = f'?v={short_hash(target)}'
        if match.group("query") != stamped:
            count += 1
        return match.group("attr") + match.group("path") + stamped + match.group("end")

    text = ATTR_RE.sub(replace, text)
    text = URL_RE.sub(replace, text)
    return text, count


def main() -> int:
    check_only = "--check" in sys.argv
    changed_files = 0

    files = sorted({f for pattern in HTML_GLOBS for f in ROOT.rglob(pattern)
                    if ".git" not in f.parts})
    for html_file in files:
        new_text, count = stamp(html_file)
        if count == 0:
            continue
        changed_files += 1
        rel = html_file.relative_to(ROOT).as_posix()
        print(f"{'would update' if check_only else 'updated'} {rel} ({count} image URL(s))")
        if not check_only:
            with open(html_file, "w", encoding="utf-8", newline="") as handle:
                handle.write(new_text)

    if changed_files == 0:
        print("all image URLs already up to date")
        return 0
    return 1 if check_only else 0


if __name__ == "__main__":
    raise SystemExit(main())
