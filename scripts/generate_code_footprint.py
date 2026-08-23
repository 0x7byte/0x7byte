from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
WIDTH, HEIGHT = 1760, 700
API_URL = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner"

THEMES = {
    "light": {
        "background": "#ffffff",
        "surface": "#f6f8fa",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#57606a",
        "accent": "#0969da",
        "accent_soft": "#54aeff",
        "track": "#eaeef2",
    },
    "dark": {
        "background": "#0d1117",
        "surface": "#161b22",
        "border": "#30363d",
        "text": "#f0f6fc",
        "muted": "#8b949e",
        "accent": "#58a6ff",
        "accent_soft": "#a5d6ff",
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
            "language": repo.get("language"),
            "size": max(repo.get("size", 0), 1),
            "updated_at": repo["updated_at"],
        }
        for repo in payload
        if not repo.get("fork") and repo["name"] != OWNER and repo.get("language")
    ]


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def draw_segmented_bar(draw: ImageDraw.ImageDraw, x: int, y: int, share: float, colors: dict) -> None:
    segments, segment_width, gap = 22, 20, 7
    filled = max(1, round((share / 100) * segments))
    for index in range(segments):
        fill = colors["accent"] if index < filled else colors["track"]
        rounded(draw, (x + index * (segment_width + gap), y, x + index * (segment_width + gap) + segment_width, y + 20), 4, fill)


def draw_panel(theme_name: str, repositories: list[dict]) -> None:
    colors = THEMES[theme_name]
    total_size = sum(repo["size"] for repo in repositories)
    language_sizes: dict[str, int] = defaultdict(int)
    for repo in repositories:
        language_sizes[repo["language"]] += repo["size"]
    languages = sorted(language_sizes.items(), key=lambda item: item[1], reverse=True)[:3]
    projects = sorted(repositories, key=lambda repo: repo["size"], reverse=True)[:4]
    latest = max(datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")) for repo in repositories)
    latest_label = latest.astimezone(timezone.utc).strftime("%d %b %Y")

    image = Image.new("RGB", (WIDTH, HEIGHT), colors["background"])
    draw = ImageDraw.Draw(image)
    regular = font(30)
    small = font(25)
    mono = font(27)
    heading = font(34, bold=True)
    section = font(28, bold=True)

    rounded(draw, (1, 1, WIDTH - 2, HEIGHT - 2), 18, colors["background"], colors["border"])
    rounded(draw, (2, 2, WIDTH - 3, 112), 18, colors["surface"])
    draw.text((58, 36), "PUBLIC CODE FOOTPRINT", fill=colors["accent"], font=heading)
    updated_width = draw.textbbox((0, 0), f"source updated {latest_label}", font=small)[2]
    draw.text((WIDTH - 58 - updated_width, 40), f"source updated {latest_label}", fill=colors["muted"], font=small)
    draw.text((58, 145), f"Language mix across {len(repositories)} public source projects", fill=colors["muted"], font=small)

    for index, (name, size) in enumerate(languages):
        y = 205 + index * 62
        share = (size / total_size) * 100
        draw.text((58, y), name, fill=colors["text"], font=mono)
        draw_segmented_bar(draw, 380, y + 5, share, colors)
        draw.text((1360, y), f"{share:.1f}%", fill=colors["muted"], font=mono)

    draw.line((58, 388, WIDTH - 58, 388), fill=colors["border"], width=2)
    draw.text((58, 420), "PUBLIC PROJECT VOLUME", fill=colors["muted"], font=section)

    for index, project in enumerate(projects):
        y = 475 + index * 48
        share = (project["size"] / total_size) * 100
        label = project["name"]
        draw.text((58, y), label, fill=colors["text"], font=small)
        rounded(draw, (680, y + 8, 1335, y + 24), 8, colors["track"])
        rounded(draw, (680, y + 8, max(690, int(680 + (share / 100) * 655)), y + 24), 8, colors["accent_soft"])
        draw.text((1360, y), f"{share:.1f}%", fill=colors["muted"], font=small)

    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/code-footprint-{theme_name}.png", format="PNG", optimize=True)


if __name__ == "__main__":
    repositories = fetch_repositories()
    if not repositories:
        raise RuntimeError("No public language-tagged repositories were available.")
    for theme in THEMES:
        draw_panel(theme, repositories)
