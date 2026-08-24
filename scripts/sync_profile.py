from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
QUERY = """
query UpdateFeed($login: String!) {
  user(login: $login) {
    login name location url
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


def compact(text: str | None) -> str:
    value = text or "Public source repository"
    return value if len(value) <= 105 else f"{value[:102].rstrip()}…"


def event_label(event: dict) -> str:
    event_type = event.get("type", "Public event")
    if event_type == "PushEvent":
        commits = max(event.get("payload", {}).get("size", 0), 1)
        return f"pushed {commits} public commit{'s' if commits != 1 else ''}"
    if event_type == "PullRequestEvent":
        return "updated a pull request"
    if event_type == "IssuesEvent":
        return "updated an issue"
    if event_type == "CreateEvent":
        return "created public source"
    if event_type == "PullRequestReviewEvent":
        return "reviewed a pull request"
    return event_type.replace("Event", "").replace("_", " ").lower()


def update_feed(events: list[dict], repositories: list[dict]) -> list[str]:
    public_names = {f"{OWNER}/{repository['name']}" for repository in repositories}
    profile_name = f"{OWNER}/{OWNER}"
    feed: list[str] = []
    seen: set[str] = set()
    for event in events:
        repository_name = event.get("repo", {}).get("name", "")
        if repository_name == profile_name or repository_name not in public_names or repository_name in seen:
            continue
        seen.add(repository_name)
        label = event_label(event)
        feed.append(f"**{format_date(event['created_at'])}** · `{repository_name.split('/', 1)[1]}` — {label}.")
        if len(feed) == 4:
            return feed
    for repository in repositories:
        if repository["name"] in seen:
            continue
        feed.append(f"**{format_date(repository['updatedAt'])}** · [`{repository['name']}`]({repository['url']}) — public source updated.")
        if len(feed) == 4:
            break
    return feed


def build_readme(user: dict, events: list[dict]) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    languages: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            languages[edge["node"]["name"]] += edge["size"]
    language_line = " · ".join(name for name, _ in languages.most_common(4)) or "No language data"
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {name}",
        "",
        "Competitive programmer building durable C foundations and moving toward AI engineering.",
        "",
        f"[GitHub profile]({user['url']}) · {user.get('location') or 'GitHub'}",
        "",
        "---",
        "",
        "## Latest public updates",
        "",
    ]
    lines.extend(f"- {entry}" for entry in update_feed(events, repositories))
    lines.extend(["", "---", "", "## Code to explore", ""])
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.append(f"- **[{repository['name']}]({repository['url']})** · `{language}` — {compact(repository.get('description'))}")
    lines.extend(
        [
            "",
            "---",
            "",
            "## Notes",
            "",
            "- Competitive programming: algorithms, data structures, and disciplined problem solving.",
            "- Current public work: C programs with file I/O, validation, and visual recursion.",
            "- AI engineering: a focused learning and building direction, grounded in systems thinking.",
            "",
            "---",
            "",
            "## Public account",
            "",
            f"`{user['repositories']['totalCount']:02d} repositories` · `{contribution_total:03d} contributions this year` · `{language_line}`",
            "",
            "<sub>Generated from public GitHub repositories and events. This profile refreshes hourly; GitHub’s native contribution calendar and activity remain below.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data(), request_json(EVENTS_URL)))
