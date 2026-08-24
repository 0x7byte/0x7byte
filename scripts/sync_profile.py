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
    login
    name
    bio
    location
    websiteUrl
    url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        description
        url
        primaryLanguage { name }
        updatedAt
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          primaryLanguage { name }
          updatedAt
          stargazerCount
        }
      }
    }
    contributionsCollection {
      contributionCalendar { totalContributions }
    }
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


def display_name(user: dict) -> str:
    return user.get("name") or user["login"]


def project_line(index: int, repo: dict) -> list[str]:
    language = (repo.get("primaryLanguage") or {}).get("name") or "source"
    detail = repo.get("description")
    heading = f"`{index:02d}` **[{repo['name']}]({repo['url']})**"
    if detail:
        heading = f"{heading} — {detail}"
    metadata = f"`{language}` · updated {format_date(repo['updatedAt'])}"
    if repo.get("stargazerCount"):
        metadata += f" · ★ {repo['stargazerCount']}"
    return [heading, metadata, ""]


def build_readme(user: dict) -> str:
    repositories = [repo for repo in user["repositories"]["nodes"] if repo["name"] != OWNER]
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to sync.")
    language_sizes: Counter[str] = Counter()
    for repo in repositories:
        for edge in repo["languages"]["edges"]:
            language_sizes[edge["node"]["name"]] += edge["size"]
    languages = " · ".join(name for name, _ in language_sizes.most_common(4)) or "No language data"
    pinned = [node for node in user["pinnedItems"]["nodes"] if node and node["name"] != OWNER]
    selection = pinned if pinned else repositories[:4]
    selection_label = "Pinned public repositories" if pinned else "Recently updated public repositories"
    bio = user.get("bio") or "Public GitHub account"
    bio_lower = bio.lower()
    identity = [
        item
        for item in (user.get("location"), user.get("websiteUrl"))
        if item and item.lower() not in bio_lower
    ]
    contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    lines = [
        f"# {display_name(user)}",
        "",
        f"[@{user['login']}]({user['url']}) · {bio}",
        "",
    ]
    if identity:
        lines.extend([" · ".join(identity), ""])
    lines.extend(
        [
            "---",
            "",
            "### public account — live sync",
            "",
            f"**{user['repositories']['totalCount']:02d}** public repositories · **{contributions:03d}** contributions in the last year",
            "",
            f"**Public code languages:** {languages}",
            "",
            "<sub>This README synchronizes from public GitHub account data every hour. Profile details, pins, public repositories, languages, descriptions, and update dates refresh automatically.</sub>",
            "",
            "---",
            "",
            f"### {selection_label.lower()}",
            "",
        ]
    )
    for index, repo in enumerate(selection, start=1):
        lines.extend(project_line(index, repo))
    remaining = [repo for repo in repositories if repo["name"] not in {repo["name"] for repo in selection}]
    if remaining:
        lines.extend(["<details>", f"<summary>All other public repositories · {len(remaining):02d}</summary>", ""])
        for index, repo in enumerate(remaining, start=len(selection) + 1):
            lines.extend(project_line(index, repo))
        lines.extend(["</details>", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(graphql()))
