from __future__ import annotations

import json
import os
import urllib.request
from hashlib import sha256
from collections import Counter
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
QUERY = """
query CompactProfile($login: String!) {
  user(login: $login) {
    login name location url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url updatedAt stargazerCount forkCount
        primaryLanguage { name }
        languages(first: 30, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name description url updatedAt primaryLanguage { name } } }
    }
    contributionsCollection { contributionCalendar { totalContributions } }
  }
}
"""

THEMES = {
    "light": {
        "background": "#ffffff", "surface": "#f6f8fa", "border": "#d0d7de", "text": "#24292f",
        "muted": "#57606a", "green": "#5eae55", "green_soft": "#85c467", "yellow": "#d6ab33", "track": "#e1e4e8",
    },
    "dark": {
        "background": "#0d1117", "surface": "#161b22", "border": "#30363d", "text": "#f0f6fc",
        "muted": "#8b949e", "green": "#70ba66", "green_soft": "#91c875", "yellow": "#d2ac46", "track": "#30363d",
    },
}


def account_data() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for the account synchronization query.")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "0x7byte-profile-sync",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in (f"/usr/share/fonts/truetype/dejavu/{filename}", f"/usr/share/fonts/dejavu/{filename}"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def concise(text: str | None, limit: int = 96) -> str:
    value = text or "Public source repository"
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def source_repositories(user: dict) -> list[dict]:
    return [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]


def public_state_key(user: dict, repositories: list[dict]) -> str:
    state = {
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "repositories": [
            {
                "name": repository["name"],
                "updatedAt": repository["updatedAt"],
                "stars": repository["stargazerCount"],
                "forks": repository["forkCount"],
                "languages": [(edge["node"]["name"], edge["size"]) for edge in repository["languages"]["edges"]],
            }
            for repository in repositories
        ],
    }
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()[:12]


def language_sizes(repositories: list[dict]) -> Counter[str]:
    sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            sizes[edge["node"]["name"]] += edge["size"]
    return sizes


def render_coding_footprint(user: dict, repositories: list[dict]) -> None:
    sizes = language_sizes(repositories)
    total = sum(sizes.values())
    if not total:
        raise RuntimeError("No public language-byte data is available for the coding footprint.")
    rows = sizes.most_common(5)
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    newest_language = (newest.get("primaryLanguage") or {}).get("name")
    latest = format_date(newest["updatedAt"])
    os.makedirs("assets", exist_ok=True)

    for theme, colors in THEMES.items():
        width, height = 1320, 310
        image = Image.new("RGB", (width, height), colors["background"])
        draw = ImageDraw.Draw(image)
        title_font, row_font, small_font, mono_font = font(29, True), font(23), font(19), font(21)
        rounded(draw, (1, 1, width - 2, height - 2), 14, colors["surface"], colors["border"])
        draw.text((40, 26), "CODING FOOTPRINT IN PUBLIC SOURCE", fill=colors["green"], font=title_font)
        live_text = f"live public data · updated {latest}"
        text_width = draw.textbbox((0, 0), live_text, font=small_font)[2]
        draw.text((width - 40 - text_width, 33), live_text, fill=colors["muted"], font=small_font)
        draw.text((40, 74), f"Language-byte share across {len(repositories)} public development projects", fill=colors["muted"], font=small_font)

        for index, (language, size) in enumerate(rows):
            y = 116 + index * 34
            share = size * 100 / total
            draw.text((40, y), language, fill=colors["text"], font=row_font)
            draw.text((250, y + 1), f"{share:05.2f}%", fill=colors["muted"], font=mono_font)
            segment_count = 23
            filled = max(1, round(segment_count * share / 100))
            for segment in range(segment_count):
                if segment >= filled:
                    fill = colors["track"]
                elif language == newest_language and segment == filled - 1:
                    fill = colors["yellow"]
                elif segment % 4 == 0:
                    fill = colors["green_soft"]
                else:
                    fill = colors["green"]
                x = 390 + segment * 29
                rounded(draw, (x, y + 1, x + 22, y + 23), 3, fill)
            draw.text((1095, y + 1), f"{size:,} bytes", fill=colors["muted"], font=mono_font)

        legend = "Green = language share  ·  Yellow = language of latest public source update"
        draw.text((40, 272), legend, fill=colors["muted"], font=small_font)
        image.save(f"assets/coding-footprint-{theme}.png", optimize=True)


def build_readme(user: dict, repositories: list[dict], state_key: str) -> str:
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_stars = sum(repository["stargazerCount"] for repository in repositories)
    total_forks = sum(repository["forkCount"] for repository in repositories)
    base = "https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets"

    lines = [
        f"# {name}",
        "",
        "**Competitive programmer · C developer · AI engineering path**",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "I use competitive programming to build algorithmic discipline and translate it into careful, practical code. My next focus is engineering the foundations needed for useful AI systems.",
        "",
        "---",
        "",
        "## Coding footprint",
        "",
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{base}/coding-footprint-dark.png?v={state_key}">',
        f'  <source media="(prefers-color-scheme: light)" srcset="{base}/coding-footprint-light.png?v={state_key}">',
        f'  <img src="{base}/coding-footprint-light.png?v={state_key}" alt="Live public-source coding footprint showing language-byte shares and the language of the most recently updated public project.">',
        "</picture>",
        "",
        "_This is calculated from public repository language bytes, so it shows source composition rather than private editor time._",
        "",
        "---",
        "",
        "## Public source index",
        "",
    ]
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.extend(
            [
                f"**[{repository['name']}]({repository['url']})** · `{language}` · updated {format_date(repository['updatedAt'])}",
                concise(repository.get("description")),
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "## Public account",
            "",
            f"{user['repositories']['totalCount']} public repositories · {total_stars} public stars · {total_forks} public forks · {contribution_total} contributions in the last year",
            "",
            "<sub>Refreshes from public GitHub API data every 15 minutes and commits only when the public data changes. GitHub’s native contribution calendar and activity remain below.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    user = account_data()
    repositories = source_repositories(user)
    render_coding_footprint(user, repositories)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories, public_state_key(user, repositories)))
