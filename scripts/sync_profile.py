from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
QUERY = """
query PublicDeveloperDashboard($login: String!) {
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
      nodes { ... on Repository { name description url updatedAt stargazerCount forkCount primaryLanguage { name } } }
    }
    contributionsCollection { contributionCalendar { totalContributions } }
  }
}
"""

ACTIVITY = {
    "PushEvent": "Commits",
    "PullRequestEvent": "Pull requests",
    "IssuesEvent": "Issues",
    "PullRequestReviewEvent": "Code reviews",
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


def concise(text: str | None, limit: int = 86) -> str:
    value = text or "Public source repository"
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def text_bar(percentage: float, width: int = 16) -> str:
    filled = max(1, round(width * percentage / 100)) if percentage else 0
    return "█" * filled + "░" * (width - filled)


def language_rows(repositories: list[dict]) -> list[tuple[str, int, str]]:
    sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            sizes[edge["node"]["name"]] += edge["size"]
    total = sum(sizes.values())
    if not total:
        return [("No public language data", 0, text_bar(0))]
    return [(name, round(size * 100 / total), text_bar(size * 100 / total)) for name, size in sizes.most_common(5)]


def activity_rows(events: list[dict]) -> tuple[list[tuple[str, int, int]], str]:
    counts: Counter[str] = Counter({label: 0 for label in ACTIVITY.values()})
    for event in events:
        label = ACTIVITY.get(event.get("type"))
        if not label:
            continue
        if event["type"] == "PushEvent":
            counts[label] += max(event.get("payload", {}).get("size", 0), 1)
        else:
            counts[label] += 1
    total = sum(counts.values())
    rows = [(label, counts[label], round(counts[label] * 100 / total) if total else 0) for label in ACTIVITY.values()]
    latest = format_date(events[0]["created_at"]) if events else "No recent public event"
    return rows, latest


def build_readme(user: dict, events: list[dict]) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    language_data = language_rows(repositories)
    activity_data, latest_activity = activity_rows(events)
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_stars = sum(repository["stargazerCount"] for repository in repositories)
    total_forks = sum(repository["forkCount"] for repository in repositories)
    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

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
        "## Developer profile",
        "",
        "| Foundation | Current direction |",
        "| --- | --- |",
        "| Algorithms, data structures, and problem solving | C projects, systems fundamentals, and applied AI engineering |",
        "",
        "## Live language usage",
        "",
        "| Language | Public code share | Text bar |",
        "| --- | ---: | --- |",
    ]
    for language, percentage, bar in language_data:
        lines.append(f"| {language} | {percentage}% | `{bar}` |")
    lines.extend(
        [
            "",
            "_Calculated from language-byte data across public, non-fork repositories._",
            "",
            "## Recent public activity",
            "",
            "| Activity type | Count | Share |",
            "| --- | ---: | ---: |",
        ]
    )
    for label, count, share in activity_data:
        lines.append(f"| {label} | {count} | {share}% |")
    lines.extend(
        [
            "",
            f"_Based on the latest 100 public GitHub events. Latest observed event: {latest_activity}._",
            "",
            "## Public projects",
            "",
            "| Project | Main language | Last update | Summary |",
            "| --- | --- | --- | --- |",
        ]
    )
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.append(
            f"| [{repository['name']}]({repository['url']}) | {language} | {format_date(repository['updatedAt'])} | {concise(repository.get('description'))} |"
        )
    lines.extend(
        [
            "",
            "## Public account snapshot",
            "",
            f"**{user['repositories']['totalCount']}** public repositories · **{total_stars}** public stars · **{total_forks}** public forks · **{contribution_total}** contributions in the last year",
            "",
            f"<sub>Refreshed {generated_at} from public GitHub account, repository, language, and event data. GitHub’s native contribution calendar and activity remain below.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data(), request_json(EVENTS_URL)))
