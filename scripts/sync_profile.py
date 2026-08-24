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


def contribution_days(user: dict) -> list[dict]:
    days = [
        day for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    return days


def contribution_version(days: list[dict]) -> str:
    data = [(day["date"], day["contributionCount"]) for day in days]
    return sha256(json.dumps(data, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def contribution_snake_svg(days: list[dict], theme: str) -> str:
    if not days:
        raise RuntimeError("No public contribution days are available for the contribution snake visual.")
    colors = {
        "dark": {"bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "text": "#c9d1d9", "muted": "#8b949e", "empty": "#21262d", "level1": "#0e4429", "level2": "#006d32", "level3": "#26a641", "level4": "#39d353", "snake": "#3dcc72", "snake_alt": "#72e39a", "head": "#8af5a8", "eye": "#0d1117", "tongue": "#ff6b6b", "food": "#f85149", "leaf": "#3fb950"},
        "light": {"bg": "#ffffff", "panel": "#f6f8fa", "line": "#d0d7de", "text": "#24292f", "muted": "#57606a", "empty": "#ebedf0", "level1": "#9be9a8", "level2": "#40c463", "level3": "#30a14e", "level4": "#216e39", "snake": "#2da44e", "snake_alt": "#1a7f37", "head": "#59c36a", "eye": "#ffffff", "tongue": "#cf222e", "food": "#cf222e", "leaf": "#1a7f37"},
    }[theme]
    maximum = max(day["contributionCount"] for day in days) or 1
    cell, gap = 13, 4
    start_x, start_y = 54, 105
    columns = max(1, (len(days) + 6) // 7)
    cells: list[str] = []
    food_index = max(range(len(days)), key=lambda index: days[index]["contributionCount"])
    for index, day in enumerate(days):
        count = day["contributionCount"]
        level = 0 if count == 0 else min(4, max(1, round(count * 4 / maximum)))
        fill = colors["empty"] if level == 0 else colors[f"level{level}"]
        column, row = divmod(index, 7)
        x, y = start_x + column * (cell + gap), start_y + row * (cell + gap)
        date_label = escape(f"{day['date']}: {count} contributions")
        cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{fill}"><title>{date_label}</title></rect>')
    route_points: list[tuple[float, float]] = []
    for column in range(columns):
        rows = range(7) if column % 2 == 0 else range(6, -1, -1)
        for row in rows:
            route_points.append((start_x + column * (cell + gap) + cell / 2, start_y + row * (cell + gap) + cell / 2))
    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in route_points)
    path_definition = f'<path id="snake-route" d="{path}"/>'
    food_column, food_row = divmod(food_index, 7)
    food_x = start_x + food_column * (cell + gap) + cell / 2
    food_y = start_y + food_row * (cell + gap) + cell / 2
    body: list[str] = []
    for segment in range(12, 0, -1):
        delay = -segment * 0.32
        size = 12 if segment < 5 else 10
        fill = colors["snake_alt"] if segment % 2 else colors["snake"]
        body.append(
            f'<g><rect x="{-size / 2:.1f}" y="{-size / 2:.1f}" width="{size}" height="{size}" rx="{size / 2.5:.1f}" fill="{fill}" stroke="{colors["bg"]}" stroke-width="1.5"/>'
            f'<animateMotion dur="16s" begin="{delay:.2f}s" repeatCount="indefinite" rotate="auto"><mpath href="#snake-route"/></animateMotion></g>'
        )
    preview_y = start_y + 3 * (cell + gap) + cell / 2
    preview_body: list[str] = []
    for segment in range(10):
        preview_x = start_x + segment * (cell + gap) + cell / 2
        fill = colors["snake_alt"] if segment % 2 else colors["snake"]
        preview_body.append(f'<circle cx="{preview_x:.1f}" cy="{preview_y:.1f}" r="6.2" fill="{fill}" stroke="{colors["bg"]}" stroke-width="1.5"/>')
    preview_head_x = start_x + 10 * (cell + gap) + cell / 2
    preview_snake = (
        f'<g><title>Snake game preview: the animated snake traverses the full calendar</title>{"".join(preview_body)}'
        f'<rect x="{preview_head_x - 9:.1f}" y="{preview_y - 8:.1f}" width="19" height="16" rx="7" fill="{colors["head"]}" stroke="{colors["bg"]}" stroke-width="2"/>'
        f'<circle cx="{preview_head_x + 3:.1f}" cy="{preview_y - 4:.1f}" r="1.8" fill="{colors["eye"]}"/><circle cx="{preview_head_x + 3:.1f}" cy="{preview_y + 4:.1f}" r="1.8" fill="{colors["eye"]}"/>'
        f'<path d="M{preview_head_x + 9:.1f},{preview_y:.1f} L{preview_head_x + 15:.1f},{preview_y - 3:.1f} M{preview_head_x + 9:.1f},{preview_y:.1f} L{preview_head_x + 15:.1f},{preview_y + 3:.1f}" stroke="{colors["tongue"]}" stroke-width="1.7" stroke-linecap="round"/>'
        f'</g>'
    )
    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    total = sum(day["contributionCount"] for day in days)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300" role="img" aria-labelledby="title desc">
<title id="title">Live full-calendar contribution snake game</title><desc id="desc">A segmented snake with eyes moves through every row of the public GitHub contribution calendar while chasing a food target on the peak contribution day.</desc>
<defs>{path_definition}</defs>
<rect width="1000" height="300" rx="16" fill="{colors['bg']}"/><rect x="1" y="1" width="998" height="298" rx="15" fill="{colors['panel']}" stroke="{colors['line']}" stroke-width="2"/>
<text x="42" y="48" fill="{colors['text']}" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="700">CONTRIBUTION SNAKE GAME</text>
<text x="42" y="75" fill="{colors['muted']}" font-family="Arial, Helvetica, sans-serif" font-size="14">live public GitHub contribution calendar · full 52-week route</text>
<text x="958" y="48" fill="{colors['food']}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="14">{total} contributions tracked</text>
<rect x="42" y="93" width="916" height="150" rx="10" fill="{colors['bg']}" stroke="{colors['line']}"/>
{''.join(cells)}
<use href="#snake-route" fill="none" stroke="{colors['snake_alt']}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.14"/>
<g transform="translate({food_x:.1f},{food_y:.1f})"><circle r="7" fill="{colors['food']}"><animate attributeName="r" values="6;8;6" dur="1.1s" repeatCount="indefinite"/></circle><path d="M0,-5 C2,-12 8,-12 8,-7" fill="none" stroke="{colors['leaf']}" stroke-width="3" stroke-linecap="round"/></g>
{preview_snake}
{''.join(body)}
<g><rect x="-10" y="-9" width="20" height="18" rx="8" fill="{colors['head']}" stroke="{colors['bg']}" stroke-width="2"/><circle cx="4" cy="-4" r="2" fill="{colors['eye']}"/><circle cx="4" cy="4" r="2" fill="{colors['eye']}"/><path d="M10,0 L16,-3 M10,0 L16,3" stroke="{colors['tongue']}" stroke-width="1.7" stroke-linecap="round"/><animateMotion dur="16s" repeatCount="indefinite" rotate="auto"><mpath href="#snake-route"/></animateMotion></g>
<line x1="42" y1="260" x2="958" y2="260" stroke="{colors['line']}" stroke-width="2"/>
<text x="42" y="283" fill="{colors['muted']}" font-family="Arial, Helvetica, sans-serif" font-size="13">{active_days} active public days · green cells = contribution level · snake visits every calendar cell · red target = peak public day</text>
</svg>'''


def render_contribution_snake(user: dict) -> str:
    days = contribution_days(user)
    version = contribution_version(days)
    os.makedirs("assets", exist_ok=True)
    for theme in ("light", "dark"):
        with open(f"assets/contribution-snake-{theme}.svg", "w", encoding="utf-8") as output:
            output.write(contribution_snake_svg(days, theme))
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


def build_readme(user: dict, repositories: list[dict], events: list[dict], contribution_snake_version: str) -> str:
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
        "## Contribution snake tracker",
        "",
        "<picture>",
        f"  <source media=\"(prefers-color-scheme: dark)\" srcset=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-snake-dark.svg?v={contribution_snake_version}\">",
        f"  <source media=\"(prefers-color-scheme: light)\" srcset=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-snake-light.svg?v={contribution_snake_version}\">",
        f"  <img src=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-snake-light.svg?v={contribution_snake_version}\" alt=\"Live snake-game tracker running across the public GitHub contribution chart.\">",
        "</picture>",
        "",
        "_A snake-game tracker crossing the public GitHub contribution chart. It refreshes with the scheduled profile sync._",
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
    contribution_snake_version = render_contribution_snake(user)
    print("Writing builder dossier profile README…", flush=True)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories, events, contribution_snake_version))
    print("Builder dossier profile synchronization complete.", flush=True)
