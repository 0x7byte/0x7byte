from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
QUERY = """
query AccessibleProfile($login: String!) {
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
EVENTS = {
    "Commits": ("PushEvent", "commits"),
    "Pull requests": ("PullRequestEvent", "pull requests"),
    "Issues": ("IssuesEvent", "issues"),
    "Reviews": ("PullRequestReviewEvent", "reviews"),
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


def activity_table(events: list[dict]) -> tuple[list[tuple[str, int, float]], str]:
    counts = {label: 0 for label in EVENTS}
    for event in events:
        for label, (event_type, _) in EVENTS.items():
            if event.get("type") == event_type:
                counts[label] += max(event.get("payload", {}).get("size", 0), 1) if label == "Commits" else 1
    total = sum(counts.values())
    rows = [(label, count, count / total * 100 if total else 0) for label, count in counts.items()]
    newest = max((event["created_at"] for event in events), default=datetime.now(timezone.utc).isoformat())
    return rows, format_date(newest)


def compact_description(description: str | None) -> str:
    value = description or "Public source repository"
    return value if len(value) <= 110 else f"{value[:107].rstrip()}…"


def activity_compass(activity: list[tuple[str, int, float]]) -> str:
    values = {label: (count, share) for label, count, share in activity}
    commits, commit_share = values["Commits"]
    pulls, pull_share = values["Pull requests"]
    issues, issue_share = values["Issues"]
    reviews, review_share = values["Reviews"]
    return "\n".join(
        [
            "```text",
            f"                       Code reviews  {reviews:>3} · {review_share:>3.0f}%",
            "                                 |",
            f"Commits  {commits:>3} · {commit_share:>3.0f}%  ----------------- + -----------------  Issues  {issues:>3} · {issue_share:>3.0f}%",
            "                                 |",
            f"                      Pull requests  {pulls:>3} · {pull_share:>3.0f}%",
            "```",
        ]
    )


def build_readme(user: dict, events: list[dict]) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    language_sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = ", ".join(name for name, _ in language_sizes.most_common(4)) or "No language data"
    activity, latest_event = activity_table(events)
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {name}",
        "",
        f"**Competitive programmer** · {user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "> Algorithmic problem solving and C foundations, with a deliberate direction toward AI engineering.",
        "",
        "---",
        "",
        "### Working profile",
        "",
        f"- **Competitive programming:** algorithms, problem solving, and performance-aware C practice.",
        "- **AI engineering direction:** building the foundations to move from systems thinking into practical AI work.",
        f"- **Public code:** {languages} across **{user['repositories']['totalCount']:02d}** repositories.",
        f"- **Latest source update:** [{repositories[0]['name']}]({repositories[0]['url']}) · {format_date(repositories[0]['updatedAt'])}.",
        "",
        "---",
        "",
        "### Public work",
        "",
    ]
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.extend(
            [
                f"- **[{repository['name']}]({repository['url']})** — {compact_description(repository.get('description'))}",
                f"  _{language} · updated {format_date(repository['updatedAt'])}_",
            ]
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "### Contribution activity",
            "",
            f"**{contribution_total:03d}** contributions in the last year · latest public event observed **{latest_event}**.",
            "",
            "#### Activity compass — live public events",
            "",
        ]
    )
    lines.extend(
        [
            activity_compass(activity),
            "",
            "> The compass is accessible text generated from the latest 100 public GitHub events. GitHub’s native annual contribution calendar and activity remain below the profile README.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data(), request_json(EVENTS_URL)))
