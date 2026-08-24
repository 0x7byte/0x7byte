from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
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


def graphql() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for the account synchronization query.")
    body = json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
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


def project_block(index: int, repository: dict) -> list[str]:
    language = (repository.get("primaryLanguage") or {}).get("name") or "source"
    description = repository.get("description") or "Public source repository"
    stars = f" · ★ {repository['stargazerCount']}" if repository.get("stargazerCount") else ""
    return [
        f"`{index:02d}` **[{repository['name']}]({repository['url']})** — {description}",
        f"`{language}` · updated {format_date(repository['updatedAt'])}{stars}",
        "",
    ]


def build_readme(user: dict) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    pinned = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER]
    selected = pinned or repositories[:4]
    language_sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = " · ".join(language for language, _ in language_sizes.most_common(4)) or "No language data"
    profile_name = user.get("name") or user["login"]
    location = user.get("location") or "GitHub"
    contribution_count = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {profile_name}",
        "",
        f"C developer · {location}",
        "",
        f"- **Profile:** [@{user['login']}]({user['url']}) · public GitHub account",
        f"- **Current source:** [{repositories[0]['name']}]({repositories[0]['url']}) · {(repositories[0].get('primaryLanguage') or {}).get('name') or 'source'}",
        f"- **Code languages:** {languages}",
        "- **Sync:** public profile and repository information refresh automatically every hour.",
        "",
        "---",
        "",
        "### Latest source updates",
        "",
    ]
    for repository in repositories[:4]:
        lines.append(f"- {format_date(repository['updatedAt'])} — [`{repository['name']}`]({repository['url']}) updated")
    lines.extend(["", "---", "", "### Current public work", ""])
    for index, repository in enumerate(selected, start=1):
        lines.extend(project_block(index, repository))
    remaining = [repository for repository in repositories if repository["name"] not in {item["name"] for item in selected}]
    if remaining:
        lines.extend(["<details>", f"<summary>Other public repositories · {len(remaining):02d}</summary>", ""])
        for index, repository in enumerate(remaining, start=len(selected) + 1):
            lines.extend(project_block(index, repository))
        lines.extend(["</details>", ""])
    lines.extend(
        [
            "---",
            "",
            "### Public activity",
            "",
            f"**{user['repositories']['totalCount']:02d}** public repositories · **{contribution_count:03d}** contributions in the last year",
            "",
            "<sub>Public profile and repository data refresh every hour. GitHub’s native contribution calendar and activity are shown below.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(graphql()))
