from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
QUERY = """
query ProfileSync($login: String!) {
  user(login: $login) {
    login name bio location url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url updatedAt stargazerCount
        primaryLanguage { name }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name description url updatedAt stargazerCount primaryLanguage { name } } }
    }
    contributionsCollection { contributionCalendar { totalContributions } }
  }
}
"""
THEMES = {
    "light": {"background": "#ffffff", "surface": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "muted": "#57606a", "green": "#5e8a62", "track": "#eaeef2"},
    "dark": {"background": "#0d1117", "surface": "#161b22", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e", "green": "#8fbd93", "track": "#30363d"},
}
EVENTS = {
    "commits": ("PushEvent", "commits"),
    "pulls": ("PullRequestEvent", "pull requests"),
    "issues": ("IssuesEvent", "issues"),
    "reviews": ("PullRequestReviewEvent", "reviews"),
}


def request_json(url: str, body: bytes | None = None) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-sync"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def account_data() -> dict:
    if not os.environ.get("GITHUB_TOKEN"):
        raise RuntimeError("GITHUB_TOKEN is required for the account synchronization query.")
    payload = request_json("https://api.github.com/graphql", json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def event_mix(events: list[dict]) -> tuple[dict[str, int], str]:
    counts = {name: 0 for name in EVENTS}
    for event in events:
        for name, (event_type, _) in EVENTS.items():
            if event.get("type") == event_type:
                counts[name] += max(event.get("payload", {}).get("size", 0), 1) if name == "commits" else 1
    newest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    return counts, format_date(newest)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'}", size)


def render_graph(theme: str, counts: dict[str, int], latest: str) -> None:
    color = THEMES[theme]
    width, height = 1760, 430
    image = Image.new("RGB", (width, height), color["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=16, fill=color["surface"], outline=color["border"], width=2)
    title, subtitle, stat, label, percent = font(34, True), font(24), font(28), font(22), font(26)
    draw.text((50, 32), "PUBLIC CONTRIBUTION MIX", fill=color["green"], font=title)
    draw.text((50, 84), "Latest 100 public GitHub events", fill=color["muted"], font=subtitle)
    order = ("commits", "pulls", "issues", "reviews")
    for index, name in enumerate(order):
        draw.text((50, 140 + index * 48), f"{counts[name]} {EVENTS[name][1]}", fill=color["text"] if index == 0 else color["muted"], font=stat)
    draw.text((50, 355), f"latest public event {latest}", fill=color["muted"], font=subtitle)
    draw.line((760, 54, 760, 375), fill=color["border"], width=2)
    center, radius = (1280, 215), 130
    for point in ((1280, 85), (1410, 215), (1280, 345), (1150, 215)):
        draw.line((center, point), fill=color["track"], width=3)
    total = sum(counts.values())
    shares = {name: (counts[name] / total * 100 if total else 0) for name in order}
    directions = {"reviews": (0, -1), "issues": (1, 0), "pulls": (0, 1), "commits": (-1, 0)}
    for name, (dx, dy) in directions.items():
        length = radius * shares[name] / 100
        end = (center[0] + dx * length, center[1] + dy * length)
        if length:
            draw.line((center, end), fill=color["green"], width=8)
            draw.ellipse((end[0] - 7, end[1] - 7, end[0] + 7, end[1] + 7), fill=color["green"], outline=color["surface"], width=2)
    draw.ellipse((1272, 207, 1288, 223), fill=color["surface"], outline=color["green"], width=4)
    labels = {"reviews": (1280, 42, "Code review"), "issues": (1460, 211, "Issues"), "pulls": (1280, 356, "Pull requests"), "commits": (1100, 211, "Commits")}
    for name, (x, y, text) in labels.items():
        share = f"{shares[name]:.0f}%"
        share_bounds = draw.textbbox((0, 0), share, font=percent)
        label_bounds = draw.textbbox((0, 0), text, font=label)
        draw.text((x - (share_bounds[2] - share_bounds[0]) / 2, y), share, fill=color["muted"], font=percent)
        draw.text((x - (label_bounds[2] - label_bounds[0]) / 2, y + 30), text, fill=color["muted"], font=label)
    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/contribution-mix-{theme}.png", optimize=True)


def build_readme(user: dict) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    languages: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            languages[edge["node"]["name"]] += edge["size"]
    language_line = " / ".join(name for name, _ in languages.most_common(4)) or "No language data"
    total_contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    current = repositories[0]
    lines = [
        f"# {user.get('name') or user['login']} · source log",
        "",
        f"> **C developer** in {user.get('location') or 'GitHub'} — a public ledger that synchronizes from this account every hour.",
        "",
        "## account pulse",
        "",
        "| signal | live public value |",
        "| :-- | :-- |",
        f"| profile | [@{user['login']}]({user['url']}) |",
        f"| source count | **{user['repositories']['totalCount']:02d}** public repositories |",
        f"| code | {language_line} |",
        f"| current source | [{current['name']}]({current['url']}) · updated {format_date(current['updatedAt'])} |",
        f"| contribution year | **{total_contributions:03d}** contributions |",
        "",
        "## source ledger",
        "",
        "| updated | repository | public scope |",
        "| :-- | :-- | :-- |",
    ]
    for repository in repositories[:4]:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        description = repository.get("description") or "Public source repository"
        lines.append(f"| {format_date(repository['updatedAt'])} | [{repository['name']}]({repository['url']}) | {language} · {description} |")
    lines.extend(["", "## contribution activity", "", "<picture>",
                  '  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-dark.png?profile=source-log-v1" />',
                  '  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=source-log-v1" />',
                  '  <img alt="Live public contribution mix" src="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=source-log-v1" width="100%" />',
                  "</picture>", "",
                  "<sub>The contribution graph is the only custom visual. It is derived from the latest 100 public GitHub events and refreshes with this profile every hour.</sub>", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    user = account_data()
    public_events = request_json(EVENTS_URL)
    counts, latest = event_mix(public_events)
    for active_theme in THEMES:
        render_graph(active_theme, counts, latest)
    with open("README.md", "w", encoding="utf-8") as file:
        file.write(build_readme(user))
