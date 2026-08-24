from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
QUERY = """
query CleanProfile($login: String!) {
  user(login: $login) {
    login name location url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url updatedAt
        primaryLanguage { name }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name description url updatedAt primaryLanguage { name } } }
    }
    contributionsCollection { contributionCalendar { totalContributions } }
  }
}
"""


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


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def concise(text: str | None) -> str:
    value = text or "Public source repository"
    return value if len(value) <= 112 else f"{value[:109].rstrip()}…"


def build_readme(user: dict) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    languages: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            languages[edge["node"]["name"]] += edge["size"]
    language_line = ", ".join(name for name, _ in languages.most_common(4)) or "No language data"
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {name}",
        "",
        "Competitive programmer and C developer, learning toward AI engineering.",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "I value precise reasoning, small correct programs, and the patience to understand systems from first principles.",
        "",
        "---",
        "",
        "## Focus",
        "",
        "**Problem solving.** Algorithms, data structures, and the habits built through competitive programming.",
        "",
        "**Programming.** C projects that practice clear control flow, validation, files, and efficient representation.",
        "",
        "**Direction.** Growing toward AI engineering through practical foundations rather than empty claims.",
        "",
        "---",
        "",
        "## Public projects",
        "",
    ]
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.extend(
            [
                f"### [{repository['name']}]({repository['url']})",
                concise(repository.get("description")),
                "",
                f"`{language}` · last updated {format_date(repository['updatedAt'])}",
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "## Public presence",
            "",
            f"{user['repositories']['totalCount']:02d} public repositories. {contribution_total:03d} contributions in the last year. Main public languages: {language_line}.",
            "",
            f"Most recently updated source: [{repositories[0]['name']}]({repositories[0]['url']}) on {format_date(repositories[0]['updatedAt'])}.",
            "",
            "<sub>Public account details refresh hourly. GitHub’s own contribution calendar and activity are shown below this README.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data()))
