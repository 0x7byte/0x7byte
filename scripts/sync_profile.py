from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import escape


OWNER = "0x7byte"
HTTP_TIMEOUT_SECONDS = 15
QUERY = """
query BuilderDossierProfile($login: String!) {
  user(login: $login) {
    login name location url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url createdAt updatedAt stargazerCount forkCount isArchived
        primaryLanguage { name }
        languages(first: 30, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name } }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def require_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for public GitHub synchronization.")
    return token


def public_events() -> list[dict]:
    request = urllib.request.Request(
        f"https://api.github.com/users/{OWNER}/events/public?per_page=30",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {require_token()}",
            "User-Agent": "0x7byte-profile-sync",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub public-events API returned an unexpected payload.")
    return payload


def account_data() -> dict:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {require_token()}",
            "Content-Type": "application/json",
            "User-Agent": "0x7byte-profile-sync",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def concise(text: str | None, limit: int = 108) -> str:
    value = " ".join((text or "Public source repository").split())
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def source_repositories(user: dict) -> list[dict]:
    return [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]


def language_sizes(repositories: list[dict]) -> Counter[str]:
    sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            sizes[edge["node"]["name"]] += edge["size"]
    return sizes


def display_language(name: str, width: int = 10) -> str:
    return (name if len(name) <= width else f"{name[: width - 1]}…").ljust(width)


def text_bar(language: str, size: int, total: int, newest_language: str | None, segments: int = 22) -> str:
    share = size * 100 / total
    filled = max(1, round(segments * share / 100))
    colored = "🟩" * filled
    if language == newest_language:
        colored = "🟩" * max(0, filled - 1) + "🟨"
    return f"{display_language(language)} {share:05.2f}%  {colored}{'▫' * (segments - filled)}  {size:,} bytes"


def native_footprint(repositories: list[dict]) -> list[str]:
    sizes = language_sizes(repositories)
    total = sum(sizes.values())
    if not total:
        raise RuntimeError("No public language-byte data is available for the coding footprint.")
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    newest_language = (newest.get("primaryLanguage") or {}).get("name")
    rows = sizes.most_common(5)
    return [
        "## Coding Footprint in Public Source",
        "",
        f"> **Live public data** · {len(repositories)} public development repositories · latest source update {format_date(newest['updatedAt'])}",
        "",
        "```text",
        *[text_bar(language, size, total, newest_language) for language, size in rows],
        "```",
        "",
        "🟩 language share · 🟨 language of the latest public source update · ▫ remaining scale",
    ]


def contribution_days(user: dict, limit: int = 28) -> list[dict]:
    days = [
        day for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    return days[-limit:]


def contribution_version(days: list[dict]) -> str:
    data = [(day["date"], day["contributionCount"]) for day in days]
    return sha256(json.dumps(data, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def contribution_blocks_svg(days: list[dict], theme: str) -> str:
    if not days:
        raise RuntimeError("No public contribution days are available for the contribution block visual.")
    colors = {
        "dark": {"bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "text": "#c9d1d9", "muted": "#8b949e", "block": "#56c271", "block_alt": "#78d58b", "accent": "#e5b94c", "empty": "#21262d"},
        "light": {"bg": "#ffffff", "panel": "#f6f8fa", "line": "#d0d7de", "text": "#24292f", "muted": "#57606a", "block": "#2da44e", "block_alt": "#55b46c", "accent": "#bf8700", "empty": "#d8dee4"},
    }[theme]
    maximum = max(day["contributionCount"] for day in days) or 1
    block_width, block_height, gap = 25, 22, 5
    start_x, floor_y = 58, 244
    blocks: list[str] = []
    for index, day in enumerate(days):
        count = day["contributionCount"]
        height = 0 if count == 0 else min(4, max(1, round(count * 4 / maximum)))
        x = start_x + index * (block_width + gap)
        blocks.append(f'<rect x="{x}" y="{floor_y - 2}" width="{block_width}" height="2" rx="1" fill="{colors['empty']}"/>')
        for level in range(height):
            y = floor_y - (level + 1) * (block_height + gap)
            delay = (index * 0.12 + level * 0.08) % 3.2
            fill = colors['accent'] if level == height - 1 and count == maximum else (colors['block_alt'] if level % 2 else colors['block'])
            label = escape(f"{day['date']}: {count} contributions")
            blocks.append(
                f'<rect x="{x}" y="{y}" width="{block_width}" height="{block_height}" rx="4" fill="{fill}" opacity="0.34"/>'
                f'<g transform="translate(0,-12)" opacity="0">'
                f'<title>{label}</title><rect x="{x}" y="{y}" width="{block_width}" height="{block_height}" rx="4" fill="{fill}"/>'
                f'<rect x="{x + 3}" y="{y + 3}" width="{block_width - 6}" height="2" rx="1" fill="#ffffff" opacity="0.28"/>'
                f'<animateTransform attributeName="transform" type="translate" values="0 -12;0 0;0 0;0 -12" keyTimes="0;0.08;0.85;1" dur="8s" begin="{delay:.2f}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.85;1" dur="8s" begin="{delay:.2f}s" repeatCount="indefinite"/>'
                f'</g>'
            )
    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    total = sum(day["contributionCount"] for day in days)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300" role="img" aria-labelledby="title desc">
<title id="title">Live contribution block run</title><desc id="desc">A game-like block animation generated from the last 28 public GitHub contribution days.</desc>
<rect width="1000" height="300" rx="16" fill="{colors['bg']}"/><rect x="1" y="1" width="998" height="298" rx="15" fill="{colors['panel']}" stroke="{colors['line']}" stroke-width="2"/>
<text x="42" y="48" fill="{colors['text']}" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="700">CONTRIBUTION BLOCK RUN</text>
<text x="42" y="75" fill="{colors['muted']}" font-family="Arial, Helvetica, sans-serif" font-size="14">live public contribution data · last 28 days</text>
<text x="958" y="48" fill="{colors['accent']}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="14">{total} blocks scored</text>
<line x1="42" y1="253" x2="958" y2="253" stroke="{colors['line']}" stroke-width="2"/>
{''.join(blocks)}
<text x="42" y="280" fill="{colors['muted']}" font-family="Arial, Helvetica, sans-serif" font-size="13">{active_days} active public days · green blocks = contribution level · yellow block = peak day</text>
</svg>'''


def render_contribution_blocks(user: dict) -> str:
    days = contribution_days(user)
    version = contribution_version(days)
    os.makedirs("assets", exist_ok=True)
    for theme in ("light", "dark"):
        with open(f"assets/contribution-blocks-{theme}.svg", "w", encoding="utf-8") as output:
            output.write(contribution_blocks_svg(days, theme))
    return version


def event_summary(event: dict) -> str:
    event_type = event.get("type", "PublicEvent")
    repository = event.get("repo", {}).get("name", "a public repository")
    payload = event.get("payload") or {}
    action = payload.get("action")
    if event_type == "PushEvent":
        count = payload.get("distinct_size") or payload.get("size") or 0
        return f"Pushed {count} commit{'s' if count != 1 else ''} to `{repository}`" if count else f"Updated `{repository}`"
    if event_type == "CreateEvent":
        return f"Created {payload.get('ref_type', 'a source item')} in `{repository}`"
    if event_type == "PublicEvent":
        return f"Made `{repository}` public"
    if event_type == "WatchEvent":
        return f"Starred `{repository}`"
    if event_type == "ForkEvent":
        return f"Fork activity in `{repository}`"
    if event_type == "PullRequestEvent":
        return f"{(action or 'Updated').capitalize()} a pull request in `{repository}`"
    if event_type == "IssuesEvent":
        return f"{(action or 'Updated').capitalize()} an issue in `{repository}`"
    if event_type == "IssueCommentEvent":
        return f"Commented on an issue in `{repository}`"
    if event_type == "ReleaseEvent":
        return f"{(action or 'Updated').capitalize()} a release in `{repository}`"
    return f"{event_type.removesuffix('Event')} activity in `{repository}`"


def recent_activity(events: list[dict], limit: int = 4) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        date = format_date(event["created_at"])
        summary = event_summary(event)
        key = (date, summary)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{date}** — {summary}")
        if len(lines) == limit:
            break
    return lines or ["- No recent public event is currently available through GitHub’s public events feed."]


def latest_contribution_date(user: dict) -> str:
    days = [
        day for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
        if day["contributionCount"] > 0
    ]
    return format_date(max(days, key=lambda day: day["date"])["date"] + "T00:00:00Z") if days else "no contribution recorded"


def project_record(repository: dict, ordinal: int, is_pinned: bool, is_open: bool) -> list[str]:
    language = (repository.get("primaryLanguage") or {}).get("name") or "source"
    markers = [f"`{language}`", f"updated {format_date(repository['updatedAt'])}"]
    if is_pinned:
        markers.append("pinned")
    if repository.get("isArchived"):
        markers.append("archived")
    star_label = "star" if repository["stargazerCount"] == 1 else "stars"
    fork_label = "fork" if repository["forkCount"] == 1 else "forks"
    return [
        f"<details{' open' if is_open else ''}>",
        f"<summary><strong>{ordinal:02d} · {repository['name']}</strong> · {language} · updated {format_date(repository['updatedAt'])}</summary>",
        "",
        concise(repository.get("description")),
        "",
        f"{' · '.join(markers)} · {repository['stargazerCount']} {star_label} · {repository['forkCount']} {fork_label}",
        "",
        f"[Open source →]({repository['url']})",
        "",
        "</details>",
        "",
    ]


def build_readme(user: dict, repositories: list[dict], events: list[dict], contribution_blocks_version: str) -> str:
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    pinned_names = {
        item["name"] for item in user["pinnedItems"]["nodes"]
        if item and item.get("name") in {repository["name"] for repository in repositories}
    }
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_stars = sum(repository["stargazerCount"] for repository in repositories)
    total_forks = sum(repository["forkCount"] for repository in repositories)
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    latest_event = event_summary(events[0]) if events else "No recent public event is currently available"
    latest_event_date = format_date(events[0]["created_at"]) if events else "—"

    lines = [
        f"# {name}",
        "",
        "<p align=\"center\">",
        "  <code>competitive programming</code> · <code>C / C++ / Java</code> · <code>Python Libraries</code> · <code>ONNX</code>",
        "</p>",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "> I use algorithmic practice to develop precision, build close-to-the-machine software in C and C++, and extend those foundations through Python data work and ONNX models.",
        "",
        "---",
        "",
        "## Live source heartbeat",
        "",
        "```text",
        f"PUBLIC REPOSITORIES  {user['repositories']['totalCount']}",
        f"SOURCE STARS         {total_stars}",
        f"SOURCE FORKS         {total_forks}",
        f"CONTRIBUTIONS        {contribution_total} in the last year",
        f"LAST CONTRIBUTION    {latest_contribution_date(user)}",
        f"LATEST SOURCE        {newest['name']} · {format_date(newest['updatedAt'])}",
        "```",
        "",
        *native_footprint(repositories),
        "",
        "---",
        "",
        "## Contribution blocks",
        "",
        "<picture>",
        f"  <source media=\"(prefers-color-scheme: dark)\" srcset=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-blocks-dark.svg?v={contribution_blocks_version}\">",
        f"  <source media=\"(prefers-color-scheme: light)\" srcset=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-blocks-light.svg?v={contribution_blocks_version}\">",
        f"  <img src=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-blocks-light.svg?v={contribution_blocks_version}\" alt=\"Live public contribution block animation for the last 28 days.\">",
        "</picture>",
        "",
        "_A building-block run animated from public GitHub contribution days. It refreshes with the scheduled profile sync._",
        "",
        "---",
        "",
        "## Public build records",
        "",
    ]
    for ordinal, repository in enumerate(repositories, start=1):
        lines.extend(project_record(repository, ordinal, repository["name"] in pinned_names, ordinal == 1))
    lines.extend(
        [
            "---",
            "",
            "## Latest GitHub trace",
            "",
            "```text",
            f"LATEST EVENT   {latest_event_date} · {latest_event.replace('`', '')}",
            "SYNC WINDOW    every 15 minutes",
            "```",
            "",
            *recent_activity(events),
            "",
            "---",
            "",
            "<sub>Live public data only: repository records, pins, source updates, language bytes, stars, forks, contributions, and activity refresh every 15 minutes. New public repositories appear after the next successful synchronization. The Coding Footprint is native text, never an image.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print("Synchronizing public account and repository data…", flush=True)
    user = account_data()
    print("Synchronizing recent public activity…", flush=True)
    repositories = source_repositories(user)
    events = public_events()
    contribution_blocks_version = render_contribution_blocks(user)
    print("Writing builder dossier profile README…", flush=True)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories, events, contribution_blocks_version))
    print("Builder dossier profile synchronization complete.", flush=True)
