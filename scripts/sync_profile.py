from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
QUERY = """
query ProfileBrief($login: String!) {
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


def brief(description: str | None) -> str:
    text = description or "Public source repository"
    return text if len(text) <= 120 else f"{text[:117].rstrip()}…"


def build_readme(user: dict) -> str:
    repositories = [repository for repository in user["repositories"]["nodes"] if repository["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    selected = [repository for repository in user["pinnedItems"]["nodes"] if repository and repository["name"] != OWNER] or repositories[:4]
    language_sizes: Counter[str] = Counter()
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = " · ".join(language for language, _ in language_sizes.most_common(4)) or "No language data"
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    name = user.get("name") or user["login"]
    lines = [
        f"# {name}",
        "",
        "**Competitive programmer · C developer · AI engineering path**",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "I use competitive programming to sharpen algorithmic thinking, then turn that discipline into reliable code. I am building from C and systems fundamentals toward practical AI engineering.",
        "",
        "---",
        "",
        "## Developer brief",
        "",
        "- **Strengths:** algorithms, data structures, problem solving, and C fundamentals.",
        "- **Now:** public C projects that emphasize clear logic, file I/O, and practical program design.",
        "- **Next:** deepen the engineering foundations needed for applied AI work.",
        "",
        "## Selected source",
        "",
    ]
    for index, repository in enumerate(selected, start=1):
        language = (repository.get("primaryLanguage") or {}).get("name") or "source"
        lines.extend(
            [
                f"**{index:02d}. [{repository['name']}]({repository['url']})** · `{language}`",
                brief(repository.get("description")),
                f"_Publicly updated {format_date(repository['updatedAt'])}_",
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "## Live account note",
            "",
            f"**{user['repositories']['totalCount']:02d}** public repositories · **{contribution_total:03d}** contributions in the last year · **{languages}**",
            "",
            f"Latest public source update: [{repositories[0]['name']}]({repositories[0]['url']}) on {format_date(repositories[0]['updatedAt'])}.",
            "",
            "<sub>This README refreshes hourly from public GitHub account data. GitHub’s native contribution calendar and activity stay below the profile.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(account_data()))
