#!/usr/bin/env python3
"""Check local Markdown links, code fences, and base skill metadata."""

from pathlib import Path
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def prose(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
        elif match:
            fence = match[1]
        else:
            lines.append(line)
    return "\n".join(lines), fence is not None


def anchors(text):
    result = set()
    counts = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", prose(text)[0], flags=re.M):
        heading = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        number = counts.get(heading, 0)
        counts[heading] = number + 1
        result.add(heading if number == 0 else f"{heading}-{number}")
    result.update(re.findall(r'\b(?:id|name)=["\']([^"\']+)', text))
    return result


def main():
    names = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    ).decode().split("\0")
    tracked = set(filter(None, names))
    directories = {parent.as_posix() for name in tracked for parent in Path(name).parents}
    files = sorted(ROOT / name for name in tracked if name.endswith(".md"))
    errors = []
    links = 0
    for path in files:
        if not path.is_file():
            errors.append(f"{path.relative_to(ROOT)}: tracked file missing from checkout")
            continue
        text = path.read_text(encoding="utf-8")
        body, unclosed = prose(text)
        if unclosed:
            errors.append(f"{path.relative_to(ROOT)}: unclosed code fence")
        body = re.sub(r"`+[^`\n]*`+", "", body)
        targets = re.findall(r"\]\(([^)]+)\)", body)
        targets += re.findall(r"^ {0,3}\[[^\]]+\]:\s*(\S+)", body, flags=re.M)
        targets += re.findall(r'\b(?:href|src)=["\']([^"\']+)', body)
        for target in targets:
            target = target.strip()
            match = re.match(r'^(?:<([^>]+)>|(\S+?))(?:\s+["\'].*["\'])?$', target)
            if match:
                target = match[1] or match[2]
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            links += 1
            local = unquote(url.path)
            name = posixpath.normpath(
                local.lstrip("/") if local.startswith("/") else
                (path.parent.relative_to(ROOT) / local).as_posix() if local else
                path.relative_to(ROOT).as_posix()
            )
            dest = ROOT / name
            if name not in tracked and name not in directories:
                errors.append(f"{path.relative_to(ROOT)}: missing tracked target {target}")
            elif not dest.exists():
                errors.append(f"{path.relative_to(ROOT)}: target missing from checkout {target}")
            elif url.fragment and dest.suffix == ".md":
                if unquote(url.fragment) not in anchors(dest.read_text(encoding="utf-8")):
                    errors.append(f"{path.relative_to(ROOT)}: missing anchor {target}")
    skill = ROOT / "skills/smoltbook/SKILL.md"
    metadata = skill.read_text(encoding="utf-8").split("---", 2)[1]
    name = re.search(r"^name: (.+)$", metadata, re.M)
    description = re.search(r"^description: (.+)$", metadata, re.M)
    if not name or name[1] != skill.parent.name or len(name[1]) > 64:
        errors.append("Base skill name must match its directory and fit in 64 characters")
    if not description or len(description[1]) > 1024:
        errors.append("Base skill description is missing or exceeds 1,024 characters")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Verified {len(files)} Markdown files, {links} local links, and base skill metadata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
