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
    track = "▫" * (segments - filled)
    return f"{display_language(language)} {share:05.2f}%  {colored}{track}  {size:,} bytes"


def native_footprint(user: dict, repositories: list[dict]) -> list[str]:
    sizes = language_sizes(repositories)
    total = sum(sizes.values())
    if not total:
        raise RuntimeError("No public language-byte data is available for the coding footprint.")
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    newest_language = (newest.get("primaryLanguage") or {}).get("name")
    rows = sizes.most_common(5)
    latest = format_date(newest["updatedAt"])
    return [
        "## 🟩 Coding Footprint in Public Source",
        "",
        f"> **Live public data** · updated {latest}",
        f"> Language-byte share across {len(repositories)} public development projects",
        "",
        "```text",
        *[text_bar(language, size, total, newest_language) for language, size in rows],
        "```",
        "",
        "🟩 language share · 🟨 language of the latest public source update · ▫ remaining scale",
        "",
        "_Calculated from public repository language bytes; it represents source composition, not private editor time._",
    ]


def build_readme(user: dict, repositories: list[dict]) -> str:
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_stars = sum(repository["stargazerCount"] for repository in repositories)
    total_forks = sum(repository["forkCount"] for repository in repositories)

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
        *native_footprint(user, repositories),
        "",
        "---",
        "",
        "## Public source index",
        "",
    ]
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
            "<sub>Refreshes from public GitHub API data every 15 minutes and commits only when the public data changes. This native footprint uses text and Unicode blocks, not generated images.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    user = account_data()
    repositories = source_repositories(user)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories))
