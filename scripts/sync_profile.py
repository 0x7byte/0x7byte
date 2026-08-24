from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
QUERY = """
query ProfileSync($login: String!) {
  user(login: $login) {
    login name bio location websiteUrl url
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
    "light": {"background": "#ffffff", "surface": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "muted": "#57606a", "green": "#5e8a62", "accent": "#d8b34c", "track": "#eaeef2"},
    "dark": {"background": "#0d1117", "surface": "#161b22", "border": "#30363d", "text": "#f0f6fc", "muted": "#8b949e", "green": "#8fbd93", "accent": "#c8a450", "track": "#30363d"},
}
EVENTS = {
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
    payload = github_request("https://api.github.com/graphql", json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def get_events() -> list[dict]:
    return github_request(EVENTS_URL)


def contribution_mix(events: list[dict]) -> tuple[dict[str, int], str]:
    counts = {name: 0 for name in EVENTS}
    for event in events:
        for name, (event_type, _) in EVENTS.items():
            if event.get("type") == event_type:
                counts[name] += max(event.get("payload", {}).get("size", 0), 1) if name == "commits" else 1
    latest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    return counts, format_date(latest)


def repo_activity(events: list[dict]) -> list[dict]:
    totals: defaultdict[str, int] = defaultdict(int)
    latest: dict[str, str] = {}
    for event in events:
        repository = event.get("repo", {}).get("name")
        if not repository or repository == f"{OWNER}/{OWNER}":
            continue
        weight = max(event.get("payload", {}).get("size", 0), 1) if event.get("type") == "PushEvent" else 1
        totals[repository] += weight
        latest[repository] = max(latest.get(repository, ""), event["created_at"])
    return [
        {"name": name.split("/", 1)[-1], "count": count, "updated": latest[name]}
        for name, count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:4]
    ]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'}", size)


def draw_panel(theme: str, title: str, subtitle: str, rows: list[tuple[str, str, float]], filename: str) -> None:
    c = THEMES[theme]
    width, height = 1760, 300
    image = Image.new("RGB", (width, height), c["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=14, fill=c["surface"], outline=c["border"], width=2)
    title_font, small, row_font = font(32, True), font(22), font(25)
    draw.text((46, 30), title, fill=c["green"], font=title_font)
    draw.text((46, 78), subtitle, fill=c["muted"], font=small)
    for index, (name, detail, share) in enumerate(rows[:4]):
        y = 125 + index * 40
        draw.text((46, y), name, fill=c["text"], font=row_font)
        draw.text((590, y + 3), detail, fill=c["muted"], font=small)
        for segment in range(22):
            x = 920 + segment * 26
            fill = c["green"] if segment < max(1, round(share * 22)) else c["track"]
            draw.rounded_rectangle((x, y + 4, x + 19, y + 23), radius=4, fill=fill)
    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/{filename}-{theme}.png", optimize=True)


def render_source_activity(theme: str, active_repos: list[dict], repositories: list[dict]) -> None:
    if active_repos:
        maximum = max(repo["count"] for repo in active_repos)
        rows = [(repo["name"], f"{repo['count']} public event units · {format_date(repo['updated'])}", repo["count"] / maximum) for repo in active_repos]
        subtitle = "Latest public GitHub event activity by repository"
        title = "RECENT PUBLIC SOURCE ACTIVITY"
    else:
        sources = []
        for repo in [repository for repository in repositories if repository["name"] != OWNER][:4]:
            size = sum(edge["size"] for edge in repo["languages"]["edges"])
            language = (repo.get("primaryLanguage") or {}).get("name") or "source"
            sources.append({"name": repo["name"], "size": max(size, 1), "detail": f"{language} · updated {format_date(repo['updatedAt'])}"})
        maximum = max(source["size"] for source in sources)
        rows = [(source["name"], source["detail"], source["size"] / maximum) for source in sources]
        subtitle = "Relative public source footprint across current repositories"
        title = "PUBLIC SOURCE FOOTPRINT"
    draw_panel(theme, title, subtitle, rows, "source-activity")


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
        _, label = EVENTS[name]
        draw.text((50, 140 + index * 48), f"{counts[name]} {label}", fill=c["text"] if index == 0 else c["muted"], font=count_font)
    draw.text((50, 355), f"latest public event {latest}", fill=c["muted"], font=subtitle)
    draw.line((760, 54, 760, 375), fill=c["border"], width=2)
    center, radius = (1280, 215), 130
    for endpoint in ((1280, 85), (1410, 215), (1280, 345), (1150, 215)):
        draw.line((center, endpoint), fill=c["track"], width=3)
    total = sum(counts.values())
    shares = {name: (counts[name] / total * 100 if total else 0) for name in ordered}
    directions = {"reviews": (0, -1), "issues": (1, 0), "pulls": (0, 1), "commits": (-1, 0)}
    for name, (dx, dy) in directions.items():
        length = radius * shares[name] / 100
        end = (center[0] + dx * length, center[1] + dy * length)
        if length:
            draw.line((center, end), fill=c["green"], width=8)
            draw.ellipse((end[0] - 7, end[1] - 7, end[0] + 7, end[1] + 7), fill=c["green"], outline=c["surface"], width=2)
    draw.ellipse((1272, 207, 1288, 223), fill=c["surface"], outline=c["green"], width=4)
    labels = {"reviews": (1280, 42, "Code review"), "issues": (1460, 211, "Issues"), "pulls": (1280, 356, "Pull requests"), "commits": (1100, 211, "Commits")}
    for name, (x, y, label) in labels.items():
        percent = f"{shares[name]:.0f}%"
        pb, lb = draw.textbbox((0, 0), percent, font=percent_font), draw.textbbox((0, 0), label, font=label_font)
        draw.text((x - (pb[2] - pb[0]) / 2, y), percent, fill=c["muted"], font=percent_font)
        draw.text((x - (lb[2] - lb[0]) / 2, y + 30), label, fill=c["muted"], font=label_font)
    os.makedirs("assets", exist_ok=True)
    image.save(f"assets/contribution-mix-{theme}.png", optimize=True)


def latest_updates(events: list[dict], repositories: list[dict]) -> list[str]:
    updates = []
    for event in events:
        repository = event.get("repo", {}).get("name", "").split("/", 1)[-1]
        if not repository or repository == OWNER:
            continue
        date = format_date(event["created_at"])
        if event["type"] == "PushEvent":
            amount = max(event.get("payload", {}).get("size", 0), 1)
            updates.append(f"{date} — **{amount} public commit{'s' if amount != 1 else ''}** in [`{repository}`](https://github.com/{OWNER}/{repository})")
        else:
            label = event["type"].replace("Event", "").replace("PullRequest", "pull request").replace("Issues", "issue").lower()
            updates.append(f"{date} — public **{label}** activity in [`{repository}`](https://github.com/{OWNER}/{repository})")
        if len(updates) == 5:
            break
    if updates:
        return updates
    return [
        f"{format_date(repo['updatedAt'])} — public source updated: [`{repo['name']}`]({repo['url']})"
        for repo in repositories[:4]
    ]


def project_lines(repositories: list[dict], selected: list[dict]) -> list[str]:
    lines = []
    for index, repo in enumerate(selected, start=1):
        language = (repo.get("primaryLanguage") or {}).get("name") or "source"
        description = repo.get("description") or "Public source repository"
        star = f" · ★ {repo['stargazerCount']}" if repo.get("stargazerCount") else ""
        lines.extend([f"`{index:02d}` **[{repo['name']}]({repo['url']})** — {description}", f"`{language}` · updated {format_date(repo['updatedAt'])}{star}", ""])
    remaining = [repo for repo in repositories if repo["name"] not in {item["name"] for item in selected}]
    if remaining:
        lines.extend(["<details>", f"<summary>Other public repositories · {len(remaining):02d}</summary>", ""])
        for index, repo in enumerate(remaining, start=len(selected) + 1):
            lines.extend(project_lines([], [repo]))
        lines.extend(["</details>", ""])
    return lines


def build_readme(user: dict, events: list[dict]) -> str:
    repositories = [repo for repo in user["repositories"]["nodes"] if repo["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to sync.")
    language_sizes: Counter[str] = Counter()
    for repo in repositories:
        for edge in repo["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = " · ".join(name for name, _ in language_sizes.most_common(4)) or "No language data"
    selected = [repo for repo in user["pinnedItems"]["nodes"] if repo and repo["name"] != OWNER] or repositories[:4]
    bio = user.get("bio") or "Public GitHub account"
    location = user.get("location")
    contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    latest_repo = repositories[0]
    lines = [
        f"# {user.get('name') or user['login']}",
        "",
        f"C developer · {location or 'GitHub'}",
        "",
        f"- **Public profile:** [@{user['login']}]({user['url']}) · synchronized from GitHub",
        f"- **Current public work:** [{latest_repo['name']}]({latest_repo['url']}) · {(latest_repo.get('primaryLanguage') or {}).get('name') or 'source'}",
        f"- **Public code languages:** {languages}",
        "- **Automatic sync:** profile, repository, pinned-work, language, and activity data refresh every hour.",
        "",
        "---",
        "",
        "### Latest public updates",
        "",
    ]
    lines.extend([f"- {update}" for update in latest_updates(events, repositories)])
    lines.extend([
        "",
        "---",
        "",
        "### Current public work",
        "",
    ])
    lines.extend(project_lines(repositories, selected))
    lines.extend([
        "---",
        "",
        "### Recent public source activity",
        "",
        "<picture>",
        '  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/source-activity-dark.png?profile=ouuan-live-v1" />',
        '  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/source-activity-light.png?profile=ouuan-live-v1" />',
        '  <img alt="Recent public source activity" src="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/source-activity-light.png?profile=ouuan-live-v1" width="100%" />',
        "</picture>",
        "",
        "---",
        "",
        "### Activity overview",
        "",
        f"**{contributions:03d}** public contributions in the last year · calculated live from GitHub.",
        "",
        "<picture>",
        '  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-dark.png?profile=ouuan-live-v2" />',
        '  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=ouuan-live-v2" />',
        '  <img alt="Live public contribution mix" src="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-mix-light.png?profile=ouuan-live-v2" width="100%" />',
        "</picture>",
        "",
        "<sub>Source activity and contribution mix use the latest 100 public GitHub events. This profile sync does not use follower counts or private account data.</sub>",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    account = graphql()
    public_events = get_events()
    mix, latest_event = contribution_mix(public_events)
    active_repos = repo_activity(public_events)
    for theme_name in THEMES:
        render_source_activity(theme_name, active_repos, account["repositories"]["nodes"])
        render_contribution_mix(theme_name, mix, latest_event)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account, public_events))
