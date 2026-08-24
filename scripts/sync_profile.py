from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


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
        "",
        "_Calculated from public repository language bytes. It represents source composition, not private editor time._",
    ]


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


def build_readme(user: dict, repositories: list[dict], events: list[dict]) -> str:
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
        "  <code>competitive programming</code> · <code>C / C++</code> · <code>Python data stack</code> · <code>ONNX models</code>",
        "</p>",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "> I use algorithmic practice to develop precision, build close-to-the-machine software in C and C++, and extend those foundations through Python data work and ONNX models.",
        "",
        "---",
        "",
        "## Builder notes",
        "",
        "**Practice:** competitive programming and algorithmic problem solving.",
        "",
        "**Core:** C and C++, custom data structures, object-oriented programming, and careful systems thinking.",
        "",
        "**Data work:** Python, NumPy, pandas, Matplotlib, and Seaborn.",
        "",
        "**Model foundation:** ONNX models.",
        "",
        "**Direction:** AI engineering as a disciplined next step, built on these foundations.",
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
    print("Writing builder dossier profile README…", flush=True)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories, events))
    print("Builder dossier profile synchronization complete.", flush=True)
