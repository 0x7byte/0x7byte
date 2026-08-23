from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
WIDTH, HEIGHT = 1760, 390
API_URL = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner"

THEMES = {
    "light": {
        "background": "#ffffff",
        "surface": "#f6f8fa",
        "border": "#d0d7de",
        "text": "#24292f",
        "muted": "#57606a",
        "green": "#6ba845",
        "yellow": "#d6a827",
        "track": "#eaeef2",
    },
    "dark": {
        "background": "#0d1117",
        "surface": "#161b22",
        "border": "#30363d",
        "text": "#f0f6fc",
        "muted": "#8b949e",
        "green": "#56d364",
        "yellow": "#e3b341",
        "track": "#21262d",
    },
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in (
        f"/usr/share/fonts/truetype/dejavu/{name}",
        f"/usr/share/fonts/dejavu/{name}",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def fetch_repositories() -> list[dict]:
    request = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "0x7byte-profile-refresh",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return [
        {
            "name": repo["name"],
            "language": repo.get("language", "Source"),
            "size": max(repo.get("size", 0), 1),
            "updated_at": repo["updated_at"],
        }
        for repo in payload
        if not repo.get("fork") and repo["name"] != OWNER and repo.get("language")
    ]


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def draw_matrix(draw: ImageDraw.ImageDraw, x: int, y: int, share: float, colors: dict, fresh: bool) -> None:
    segments, width, gap = 22, 24, 7
    filled = max(1, round((share / 100) * segments))
    for index in range(segments):
        if index >= filled:
            fill = colors["track"]
        elif fresh and index == filled - 1:
            fill = colors["yellow"]
        else:
            fill = colors["green"]
        rounded(draw, (x + index * (width + gap), y, x + index * (width + gap) + width, y + 21), 4, fill)


def draw_panel(theme_name: str, repositories: list[dict]) -> None:
    colors = THEMES[theme_name]
    total_size = sum(repo["size"] for repo in repositories)
    projects = sorted(repositories, key=lambda repo: repo["size"], reverse=True)[:4]
    newest = max(projects, key=lambda repo: datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")))
    latest = max(datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")) for repo in repositories)
    latest_label = latest.astimezone(timezone.utc).strftime("%d %b %Y")

    image = Image.new("RGB", (WIDTH, HEIGHT), colors["background"])
    draw = ImageDraw.Draw(image)
    title_font = font(34, bold=True)
    row_font = font(27)
    small_font = font(24)
    mono_font = font(25)

    rounded(draw, (1, 1, WIDTH - 2, HEIGHT - 2), 16, colors["surface"], colors["border"])
    draw.text((50, 30), "PUBLIC SOURCE ACTIVITY", fill=colors["green"], font=title_font)
    latest_text = f"source updated {latest_label}"
    latest_width = draw.textbbox((0, 0), latest_text, font=small_font)[2]
    draw.text((WIDTH - 50 - latest_width, 36), latest_text, fill=colors["muted"], font=small_font)
    draw.text((50, 88), f"Relative public source mix across {len(repositories)} projects", fill=colors["muted"], font=small_font)

    for index, project in enumerate(projects):
        y = 135 + index * 54
        share = (project["size"] / total_size) * 100
        draw.text((50, y), project["name"], fill=colors["text"], font=row_font)
        draw.text((550, y), project["language"], fill=colors["muted"], font=mono_font)
        draw_matrix(draw, 620, y + 3, share, colors, project["name"] == newest["name"])
        draw.text((1370, y), f"{share:.1f}%", fill=colors["muted"], font=mono_font)

    draw.text((50, 340), "Green = public source share · Yellow = most recently updated project", fill=colors["muted"], font=small_font)
    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/code-footprint-{theme_name}.png", format="PNG", optimize=True)


if __name__ == "__main__":
    repositories = fetch_repositories()
    if not repositories:
        raise RuntimeError("No public language-tagged repositories were available.")
    for theme in THEMES:
        draw_panel(theme, repositories)
