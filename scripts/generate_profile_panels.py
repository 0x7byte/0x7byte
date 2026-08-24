from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
REPO_URL = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner"
EVENT_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
THEMES = {
    "light": {"background": "#ffffff", "surface": "#f6f8fa", "surface2": "#ffffff", "border": "#d0d7de", "text": "#24292f", "muted": "#57606a", "green": "#5e8a62", "yellow": "#c7a04c", "track": "#eaeef2"},
    "dark": {"background": "#0d1117", "surface": "#161b22", "surface2": "#0d1117", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e", "green": "#7fa784", "yellow": "#c8a450", "track": "#21262d"},
}


def get_json(url: str) -> list[dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-refresh"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def public_repositories() -> list[dict]:
    repos = get_json(REPO_URL)
    return [
        {
            "name": repo["name"],
            "language": repo.get("language", "Source"),
            "size": max(repo.get("size", 0), 1),
            "description": repo.get("description") or "Public source repository",
            "updated_at": repo["updated_at"],
        }
        for repo in repos
        if not repo.get("fork") and repo["name"] != OWNER and repo.get("language")
    ]


def public_commit_count() -> tuple[int, str]:
    events = get_json(EVENT_URL)
    commits = sum(max(event.get("payload", {}).get("size", 0), 1) for event in events if event.get("type") == "PushEvent")
    latest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    return commits, datetime.fromisoformat(latest.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def update_date(repo: dict) -> str:
    return datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def draw_profile_summary(theme: str, repos: list[dict], commits: int, latest: str) -> None:
    c = THEMES[theme]
    width, height = 1760, 300
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    name, role, label, value, small = font(56, True), font(30), font(20, True), font(44, True), font(22)
    language = Counter(repo["language"] for repo in repos).most_common(1)[0][0]
    rounded(draw, (1, 1, width - 2, height - 2), 16, c["surface"], c["border"])
    draw.text((50, 38), "MHSAN", fill=c["text"], font=name)
    draw.text((52, 112), "C developer · Rangpur, Bangladesh", fill=c["muted"], font=role)
    draw.text((52, 162), "C  ·  raylib  ·  Git  ·  Bash  ·  Linux", fill=c["green"], font=small)
    draw.text((52, 222), f"live public signal · refreshed {latest}", fill=c["muted"], font=small)
    card_x = 850
    for index, (number, caption) in enumerate(((str(len(repos)).zfill(2), "PUBLIC SOURCES"), (str(commits).zfill(2), "RECENT COMMITS"), (language, "PRIMARY LANGUAGE"))):
        x = card_x + index * 285
        rounded(draw, (x, 54, x + 240, 246), 14, c["surface2"], c["border"])
        draw.text((x + 24, 84), caption, fill=c["muted"], font=label)
        draw.text((x + 24, 132), number, fill=c["green"] if index < 2 else c["text"], font=value if index < 2 else font(36, True))
        draw.text((x + 24, 195), "public GitHub data", fill=c["muted"], font=small)
    image.save(f"assets/profile-summary-{theme}.png", optimize=True)


def draw_source_index(theme: str, repos: list[dict]) -> None:
    c = THEMES[theme]
    width, height = 1760, 430
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    title, row, meta, body = font(34, True), font(26, True), font(22), font(24)
    projects = sorted(repos, key=lambda repo: repo["size"], reverse=True)[:4]
    rounded(draw, (1, 1, width - 2, height - 2), 16, c["surface"], c["border"])
    draw.text((50, 30), "SOURCE INDEX", fill=c["green"], font=title)
    draw.text((50, 82), "Selected public repositories", fill=c["muted"], font=meta)
    for index, repo in enumerate(projects):
        y = 125 + index * 69
        if index:
            draw.line((50, y - 17, width - 50, y - 17), fill=c["border"], width=1)
        number = f"{index + 1:02d}"
        draw.text((52, y), number, fill=c["green"], font=meta)
        draw.text((130, y - 4), repo["name"], fill=c["text"], font=row)
        draw.text((780, y), trim(repo["description"], 48), fill=c["muted"], font=body)
        draw.text((1470, y), repo["language"], fill=c["green"], font=meta)
        draw.text((1470, y + 30), update_date(repo), fill=c["muted"], font=meta)
    image.save(f"assets/source-index-{theme}.png", optimize=True)


def draw_source_activity(theme: str, repos: list[dict]) -> None:
    c = THEMES[theme]
    width, height = 1760, 390
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    title, row, small, mono = font(34, True), font(27), font(24), font(25)
    total = sum(repo["size"] for repo in repos)
    projects = sorted(repos, key=lambda repo: repo["size"], reverse=True)[:4]
    newest = max(projects, key=lambda repo: repo["updated_at"])
    latest = update_date(max(repos, key=lambda repo: repo["updated_at"]))
    rounded(draw, (1, 1, width - 2, height - 2), 16, c["surface"], c["border"])
    draw.text((50, 30), "PUBLIC SOURCE ACTIVITY", fill=c["green"], font=title)
    latest_label = f"source updated {latest}"
    latest_width = draw.textbbox((0, 0), latest_label, font=small)[2]
    draw.text((width - 50 - latest_width, 36), latest_label, fill=c["muted"], font=small)
    draw.text((50, 88), f"Relative public source mix across {len(repos)} projects", fill=c["muted"], font=small)
    for index, repo in enumerate(projects):
        y, share = 135 + index * 54, (repo["size"] / total) * 100
        draw.text((50, y), repo["name"], fill=c["text"], font=row)
        draw.text((550, y), repo["language"], fill=c["muted"], font=mono)
        filled = max(1, round((share / 100) * 22))
        for segment in range(22):
            fill = c["track"] if segment >= filled else (c["yellow"] if repo["name"] == newest["name"] and segment == filled - 1 else c["green"])
            x = 620 + segment * 31
            rounded(draw, (x, y + 3, x + 24, y + 24), 4, fill)
        draw.text((1370, y), f"{share:.1f}%", fill=c["muted"], font=mono)
    draw.text((50, 340), "Green = public source share · Yellow = most recently updated project", fill=c["muted"], font=small)
    image.save(f"assets/code-footprint-{theme}.png", optimize=True)


if __name__ == "__main__":
    os.makedirs("assets", exist_ok=True)
    repositories = public_repositories()
    if not repositories:
        raise RuntimeError("No public language-tagged repositories were available.")
    commits, latest_event = public_commit_count()
    for theme_name in THEMES:
        draw_profile_summary(theme_name, repositories, commits, latest_event)
        draw_source_activity(theme_name, repositories)
        draw_source_index(theme_name, repositories)
