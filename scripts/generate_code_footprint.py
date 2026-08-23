from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
REPO_URL = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner"
EVENT_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"

THEMES = {
    "light": {"background": "#ffffff", "surface": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "muted": "#57606a", "green": "#5e8a62", "yellow": "#c7a04c", "track": "#eaeef2", "axis": "#5f8b69", "fill": "#d7e6d9"},
    "dark": {"background": "#0d1117", "surface": "#161b22", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e", "green": "#7fa784", "yellow": "#c8a450", "track": "#21262d", "axis": "#71987a", "fill": "#203826"},
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in (f"/usr/share/fonts/truetype/dejavu/{filename}", f"/usr/share/fonts/dejavu/{filename}"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def get_json(url: str) -> list[dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-refresh"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def public_repositories() -> list[dict]:
    return [{"name": repo["name"], "language": repo.get("language", "Source"), "size": max(repo.get("size", 0), 1), "updated_at": repo["updated_at"]} for repo in get_json(REPO_URL) if not repo.get("fork") and repo["name"] != OWNER and repo.get("language")]


def contribution_counts() -> tuple[dict[str, int], str]:
    counts = {"Commits": 0, "Pull requests": 0, "Issues": 0, "Code review": 0}
    events = get_json(EVENT_URL)
    latest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    for event in events:
        kind = event.get("type")
        if kind == "PushEvent":
            counts["Commits"] += max(event.get("payload", {}).get("size", 0), 1)
        elif kind == "PullRequestEvent":
            counts["Pull requests"] += 1
        elif kind == "IssuesEvent":
            counts["Issues"] += 1
        elif kind in {"PullRequestReviewEvent", "PullRequestReviewCommentEvent"}:
            counts["Code review"] += 1
    return counts, latest


def draw_matrix(theme: str, repositories: list[dict]) -> None:
    c = THEMES[theme]
    width, height = 1760, 390
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    title, row, small, mono = font(34, True), font(27), font(24), font(25)
    total = sum(repo["size"] for repo in repositories)
    projects = sorted(repositories, key=lambda repo: repo["size"], reverse=True)[:4]
    newest = max(projects, key=lambda repo: datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")))
    latest = max(datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")) for repo in repositories).astimezone(timezone.utc).strftime("%d %b %Y")

    rounded(draw, (1, 1, width - 2, height - 2), 16, c["surface"], c["border"])
    draw.text((50, 30), "PUBLIC SOURCE ACTIVITY", fill=c["green"], font=title)
    update_text = f"source updated {latest}"
    draw.text((width - 50 - draw.textbbox((0, 0), update_text, font=small)[2], 36), update_text, fill=c["muted"], font=small)
    draw.text((50, 88), f"Relative public source mix across {len(repositories)} projects", fill=c["muted"], font=small)
    for index, project in enumerate(projects):
        y, share = 135 + index * 54, (project["size"] / total) * 100
        draw.text((50, y), project["name"], fill=c["text"], font=row)
        draw.text((550, y), project["language"], fill=c["muted"], font=mono)
        filled = max(1, round((share / 100) * 22))
        for segment in range(22):
            fill = c["track"] if segment >= filled else (c["yellow"] if project["name"] == newest["name"] and segment == filled - 1 else c["green"])
            x = 620 + segment * 31
            rounded(draw, (x, y + 3, x + 24, y + 24), 4, fill)
        draw.text((1370, y), f"{share:.1f}%", fill=c["muted"], font=mono)
    draw.text((50, 340), "Green = public source share · Yellow = most recently updated project", fill=c["muted"], font=small)
    image.save(f"assets/code-footprint-{theme}.png", optimize=True)


def point(center: tuple[float, float], angle: float, radius: float) -> tuple[float, float]:
    return center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius


def draw_radar(theme: str, counts: dict[str, int], latest_event: str) -> None:
    c = THEMES[theme]
    width, height = 1760, 430
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    title, body, small, label = font(34, True), font(25), font(22), font(24)
    total = sum(counts.values())
    shares = {name: (value / total * 100 if total else 0) for name, value in counts.items()}
    recent = datetime.fromisoformat(latest_event.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")
    center, radius = (1270, 230), 128
    axes = {"Code review": -math.pi / 2, "Issues": 0, "Pull requests": math.pi / 2, "Commits": math.pi}

    rounded(draw, (1, 1, width - 2, height - 2), 16, c["surface"], c["border"])
    draw.text((50, 30), "PUBLIC CONTRIBUTION MIX", fill=c["green"], font=title)
    draw.text((50, 84), "Recent public GitHub events", fill=c["muted"], font=small)
    summary = [f"{counts['Commits']} commits", f"{counts['Pull requests']} pull requests", f"{counts['Issues']} issues", f"{counts['Code review']} reviews"]
    for index, line in enumerate(summary):
        draw.text((50, 140 + index * 42), line, fill=c["text"] if index == 0 else c["muted"], font=body)
    update = f"latest public event {recent}"
    draw.text((50, 348), update, fill=c["muted"], font=small)
    draw.line((770, 62, 770, height - 62), fill=c["border"], width=2)

    for name, angle in axes.items():
        endpoint = point(center, angle, radius)
        draw.line((center[0], center[1], endpoint[0], endpoint[1]), fill=c["axis"], width=4)
        share = shares[name]
        dot = point(center, angle, radius * (share / 100))
        draw.line((center[0], center[1], dot[0], dot[1]), fill=c["green"], width=7)
        draw.ellipse((dot[0] - 7, dot[1] - 7, dot[0] + 7, dot[1] + 7), fill=c["green"], outline=c["background"], width=2)
        text = f"{share:.0f}%\n{name}"
        bbox = draw.multiline_textbbox((0, 0), text, font=label, align="center", spacing=2)
        label_point = point(center, angle, radius + 40)
        draw.multiline_text((label_point[0] - (bbox[2] - bbox[0]) / 2, label_point[1] - (bbox[3] - bbox[1]) / 2), text, fill=c["muted"], font=label, align="center", spacing=2)
    draw.ellipse((center[0] - 9, center[1] - 9, center[0] + 9, center[1] + 9), fill=c["surface"], outline=c["axis"], width=4)
    image.save(f"assets/contribution-mix-{theme}.png", optimize=True)


if __name__ == "__main__":
    repositories = public_repositories()
    if not repositories:
        raise RuntimeError("No public language-tagged repositories were available.")
    counts, latest_event = contribution_counts()
    os.makedirs("assets", exist_ok=True)
    for theme_name in THEMES:
        draw_matrix(theme_name, repositories)
        draw_radar(theme_name, counts, latest_event)
