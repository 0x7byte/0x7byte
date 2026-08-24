from __future__ import annotations

import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone


OWNER = "0x7byte"
REPOSITORIES_URL = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner"
EVENTS_URL = f"https://api.github.com/users/{OWNER}/events/public?per_page=100"
PRIORITY = {
    "fractal_tree": 0,
    "RLE_Compressor-Decompressor": 1,
    "student-hall-management-system": 2,
    "vehicle-management-system": 3,
}
FALLBACK_NOTES = {
    "fractal_tree": "recursive visualizer with raylib",
    "RLE_Compressor-Decompressor": "reversible run-length encoding CLI",
    "student-hall-management-system": "file-backed hall management system",
    "vehicle-management-system": "validated vehicle record management",
}


def get_json(url: str) -> list[dict]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "0x7byte-profile-refresh"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def source_repositories() -> list[dict]:
    repos = get_json(REPOSITORIES_URL)
    selected = [
        repo
        for repo in repos
        if not repo.get("fork") and repo["name"] != OWNER and repo.get("language")
    ]
    return sorted(selected, key=lambda repo: (PRIORITY.get(repo["name"], 99), repo["name"].lower()))


def recent_push_commit_count() -> int:
    events = get_json(EVENTS_URL)
    return sum(
        max(event.get("payload", {}).get("size", 0), 1)
        for event in events
        if event.get("type") == "PushEvent"
    )


def write_readme(repos: list[dict], push_commits: int) -> None:
    if not repos:
        raise RuntimeError("No public language-tagged source repositories were available.")
    primary_language = Counter(repo["language"] for repo in repos).most_common(1)[0][0]
    latest_source = max(repos, key=lambda repo: repo["updated_at"])
    lines = [
        "# mhsan",
        "",
        "C developer · Rangpur, Bangladesh",
        "",
        "> **Live public source snapshot** · refreshed daily from GitHub public data",
        ">",
        f"> **{len(repos):02d}** public sources · **{push_commits:02d}** recent public push commits · **{primary_language}** primary language · source updated **{format_date(latest_source['updated_at'])}**",
        "",
        "### Source index",
        "",
    ]
    for index, repo in enumerate(repos, start=1):
        note = repo.get("description") or FALLBACK_NOTES.get(repo["name"], "public source repository")
        lines.append(f"`{index:02d}` **[{repo['name']}]({repo['html_url']})** — {note} <br>")
        lines.append(f"`{repo['language']}` · updated {format_date(repo['updated_at'])}")
        lines.append("")
    lines.extend(
        [
            "---",
            "",
            "### Contribution stream",
            "",
            "<picture>",
            '  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-snake-dark.svg" />',
            '  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-snake-light.svg" />',
            '  <img alt="Contribution activity animation" src="https://raw.githubusercontent.com/0x7byte/0x7byte/main/assets/contribution-snake-dark.svg" width="100%" />',
            "</picture>",
            "",
            "<sub>The text snapshot and contribution stream refresh automatically. Recent push commits are counted from the latest 100 public GitHub events.</sub>",
            "",
        ]
    )
    with open("README.md", "w", encoding="utf-8") as output:
        output.write("\n".join(lines))


if __name__ == "__main__":
    write_readme(source_repositories(), recent_push_commit_count())
