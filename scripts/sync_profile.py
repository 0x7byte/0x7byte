from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
QUERY = """
query CompactProfile($login: String!) {
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


def concise(text: str | None, limit: int = 96) -> str:
    value = text or "Public source repository"
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def text_bar(percentage: float, width: int = 20) -> str:
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


def build_readme(user: dict) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    language_data = language_rows(repositories)
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
        "## Coding footprint in public source",
        "",
        "| Language | Public code share | Footprint |",
        "| --- | ---: | --- |",
    ]
    for language, percentage, bar in language_data:
        lines.append(f"| {language} | {percentage}% | `{bar}` |")
    lines.extend(
        [
            "",
            "_Live language-byte share across public, non-fork repositories. This is a public-source footprint, not a time tracker._",
            "",
            "---",
            "",
            "## Public source index",
            "",
        ]
    )
    for repository in selected:
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.extend(
            [
                f"**[{repository['name']}]({repository['url']})** · `{language}` · updated {format_date(repository['updatedAt'])}",
                concise(repository.get("description")),
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "## Public account",
            "",
            f"{user['repositories']['totalCount']} public repositories · {total_stars} public stars · {total_forks} public forks · {contribution_total} contributions in the last year",
            "",
            f"<sub>Refreshed {generated_at} from public GitHub account, repository, and language data. GitHub’s native contribution calendar and activity remain below.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data()))
