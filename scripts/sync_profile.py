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
    login
    name
    bio
    location
    websiteUrl
    url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        description
        url
        primaryLanguage { name }
        updatedAt
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          primaryLanguage { name }
          updatedAt
          stargazerCount
        }
      }
    }
    contributionsCollection {
      contributionCalendar { totalContributions }
    }
  }
}
"""
THEMES = {
    "light": {"background": "#ffffff", "surface": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "muted": "#57606a", "green": "#5e8a62", "track": "#d8dee4"},
    "dark": {"background": "#0d1117", "surface": "#161b22", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e", "green": "#8fbd93", "track": "#30363d"},
}
EVENT_LABELS = {
    "commits": ("PushEvent", "commits"),
    "pulls": ("PullRequestEvent", "pull requests"),
    "issues": ("IssuesEvent", "issues"),
    "reviews": ("PullRequestReviewEvent", "reviews"),
}


def github_request(url: str, body: bytes | None = None) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-sync"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def graphql() -> dict:
    if not os.environ.get("GITHUB_TOKEN"):
        raise RuntimeError("GITHUB_TOKEN is required for the account synchronization query.")
    body = json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8")
    payload = github_request("https://api.github.com/graphql", body)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def public_event_mix() -> tuple[dict[str, int], str]:
    events = github_request(EVENTS_URL)
    counts = {name: 0 for name in EVENT_LABELS}
    for event in events:
        for name, (event_type, _) in EVENT_LABELS.items():
            if event.get("type") == event_type:
                counts[name] += max(event.get("payload", {}).get("size", 0), 1) if name == "commits" else 1
    latest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    return counts, format_date(latest)


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def render_contribution_mix(theme: str, counts: dict[str, int], latest: str) -> None:
    c = THEMES[theme]
    width, height = 1760, 430
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=16, fill=c["surface"], outline=c["border"], width=2)
    title, subtitle, count_font, label_font, percent_font = font(34, True), font(24), font(28), font(22), font(26)
    draw.text((50, 32), "PUBLIC CONTRIBUTION MIX", fill=c["green"], font=title)
    draw.text((50, 84), "Latest 100 public GitHub events", fill=c["muted"], font=subtitle)
    ordered = ("commits", "pulls", "issues", "reviews")
    for index, name in enumerate(ordered):
        _, label = EVENT_LABELS[name]
        y = 140 + index * 48
        draw.text((50, y), f"{counts[name]} {label}", fill=c["text"] if index == 0 else c["muted"], font=count_font)
    draw.text((50, 355), f"latest public event {latest}", fill=c["muted"], font=subtitle)
    draw.line((760, 54, 760, 375), fill=c["border"], width=2)
    center = (1280, 215)
    radius = 130
    for endpoint in ((center[0], center[1] - radius), (center[0] + radius, center[1]), (center[0], center[1] + radius), (center[0] - radius, center[1])):
        draw.line((center, endpoint), fill=c["track"], width=3)
    total = sum(counts.values())
    shares = {name: (counts[name] / total * 100 if total else 0) for name in ordered}
    directions = {"reviews": (0, -1), "issues": (1, 0), "pulls": (0, 1), "commits": (-1, 0)}
    for name, (dx, dy) in directions.items():
        length = radius * (shares[name] / 100)
        end = (center[0] + dx * length, center[1] + dy * length)
        if length:
            draw.line((center, end), fill=c["green"], width=8)
            draw.ellipse((end[0] - 7, end[1] - 7, end[0] + 7, end[1] + 7), fill=c["green"], outline=c["surface"], width=2)
        else:
            draw.ellipse((center[0] - 4, center[1] - 4, center[0] + 4, center[1] + 4), fill=c["track"])
    draw.ellipse((center[0] - 8, center[1] - 8, center[0] + 8, center[1] + 8), fill=c["surface"], outline=c["green"], width=4)
    labels = {
        "reviews": (center[0], 42, "Code review"),
        "issues": (center[0] + 180, center[1] - 4, "Issues"),
        "pulls": (center[0], 356, "Pull requests"),
        "commits": (center[0] - 180, center[1] - 4, "Commits"),
    }
    for name, (x, y, label) in labels.items():
        percent = f"{shares[name]:.0f}%"
        percent_box = draw.textbbox((0, 0), percent, font=percent_font)
        label_box = draw.textbbox((0, 0), label, font=label_font)
        draw.text((x - (percent_box[2] - percent_box[0]) / 2, y), percent, fill=c["muted"], font=percent_font)
        draw.text((x - (label_box[2] - label_box[0]) / 2, y + 30), label, fill=c["muted"], font=label_font)
    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/contribution-mix-{theme}.png", optimize=True)


def display_name(user: dict) -> str:
    return user.get("name") or user["login"]


def project_line(index: int, repo: dict) -> list[str]:
    language = (repo.get("primaryLanguage") or {}).get("name") or "source"
    detail = repo.get("description")
    heading = f"`{index:02d}` **[{repo['name']}]({repo['url']})**"
    if detail:
        heading = f"{heading} — {detail}"
    metadata = f"`{language}` · updated {format_date(repo['updatedAt'])}"
    if repo.get("stargazerCount"):
        metadata += f" · ★ {repo['stargazerCount']}"
    return [heading, metadata, ""]


def build_readme(user: dict) -> str:
    repositories = [repo for repo in user["repositories"]["nodes"] if repo["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to sync.")
    language_sizes: Counter[str] = Counter()
    for repo in repositories:
        for edge in repo["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = " · ".join(name for name, _ in language_sizes.most_common(4)) or "No language data"
    pinned = [node for node in user["pinnedItems"]["nodes"] if node and node["name"] != OWNER]
    selection = pinned if pinned else repositories[:4]
    selection_label = "Pinned public repositories" if pinned else "Recently updated public repositories"
    bio = user.get("bio") or "Public GitHub account"
    identity = [item for item in (user.get("location"), user.get("websiteUrl")) if item and item.lower() not in bio.lower()]
    contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {display_name(user)}",
        "",
        f"[@{user['login']}]({user['url']}) · {bio}",
        "",
    ]
    if identity:
        lines.extend([" · ".join(identity), ""])
    lines.extend(
        [
            "---",
            "",
            "### public account — live sync",
            "",
            f"**{user['repositories']['totalCount']:02d}** public repositories · **{contributions:03d}** contributions in the last year",
            "",
            f"**Public code languages:** {languages}",
            "",
            "<sub>This README synchronizes from public GitHub account data every hour. Profile details, pins, public repositories, languages, descriptions, and update dates refresh automatically.</sub>",
            "",
            "---",
            "",
            "### contribution activity",
            "",
            "<picture>",
            '  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-dark.png?profile=account-live-v1" />',
            '  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=account-live-v1" />',
            '  <img alt="Live public contribution mix" src="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=account-live-v1" width="100%" />',
            "</picture>",
            "",
            "<sub>Contribution mix is calculated from the latest 100 public GitHub events and refreshes with this account sync.</sub>",
            "",
            "---",
            "",
            f"### {selection_label.lower()}",
            "",
        ]
    )
    for index, repo in enumerate(selection, start=1):
        lines.extend(project_line(index, repo))
    remaining = [repo for repo in repositories if repo["name"] not in {repo["name"] for repo in selection}]
    if remaining:
        lines.extend(["<details>", f"<summary>All other public repositories · {len(remaining):02d}</summary>", ""])
        for index, repo in enumerate(remaining, start=len(selection) + 1):
            lines.extend(project_line(index, repo))
        lines.extend(["</details>", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    profile = graphql()
    mix, latest_event = public_event_mix()
    for theme_name in THEMES:
        render_contribution_mix(theme_name, mix, latest_event)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(profile))
