from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from PIL import Image, ImageDraw, ImageFont


OWNER = "0x7byte"
HTTP_TIMEOUT_SECONDS = 15
QUERY = """
query BuilderDossierProfile($login: String!) {
  user(login: $login) {
    login name location url
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url createdAt updatedAt stargazerCount forkCount isArchived
        primaryLanguage { name }
        languages(first: 30, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name } }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def require_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for public GitHub synchronization.")
    return token


def public_events() -> list[dict]:
    request = urllib.request.Request(
        f"https://api.github.com/users/{OWNER}/events/public?per_page=30",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {require_token()}",
            "User-Agent": "0x7byte-profile-sync",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub public-events API returned an unexpected payload.")
    return payload


def account_data() -> dict:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {require_token()}",
            "Content-Type": "application/json",
            "User-Agent": "0x7byte-profile-sync",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %Y")


def concise(text: str | None, limit: int = 108) -> str:
    value = " ".join((text or "Public source repository").split())
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
    return f"{display_language(language)} {share:05.2f}%  {colored}{'▫' * (segments - filled)}  {size:,} bytes"


def native_footprint(repositories: list[dict]) -> list[str]:
    sizes = language_sizes(repositories)
    total = sum(sizes.values())
    if not total:
        raise RuntimeError("No public language-byte data is available for the coding footprint.")
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    newest_language = (newest.get("primaryLanguage") or {}).get("name")
    rows = sizes.most_common(5)
    return [
        "## Coding Footprint in Public Source",
        "",
        f"> **Live public data** · {len(repositories)} public development repositories · latest source update {format_date(newest['updatedAt'])}",
        "",
        "```text",
        *[text_bar(language, size, total, newest_language) for language, size in rows],
        "```",
        "",
        "🟩 language share · 🟨 language of the latest public source update · ▫ remaining scale",
    ]


def contribution_days(user: dict) -> list[dict]:
    days = [
        day for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    return days


def contribution_version(days: list[dict]) -> str:
    data = {
        "renderer": "active-cell-snake-v1",
        "days": [(day["date"], day["contributionCount"]) for day in days],
    }
    return sha256(json.dumps(data, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def grid_step_path(start: tuple[int, int], target: tuple[int, int], horizontal_first: bool) -> list[tuple[int, int]]:
    column, row = start
    target_column, target_row = target
    path = [start]
    axes = (("column", target_column), ("row", target_row)) if horizontal_first else (("row", target_row), ("column", target_column))
    for axis, target_value in axes:
        while (column if axis == "column" else row) != target_value:
            if axis == "column":
                column += 1 if target_value > column else -1
            else:
                row += 1 if target_value > row else -1
            path.append((column, row))
    return path


def active_cell_route(days: list[dict], columns: int) -> tuple[list[tuple[int, int]], set[tuple[int, int]], list[tuple[int, int]]]:
    active = [index for index, day in enumerate(days) if day["contributionCount"] > 0]
    active_points = [(index // 7, index % 7) for index in active]
    if not active_points:
        return [(0, 3)], set(), []
    ordered = sorted(
        active_points,
        key=lambda point: sha256(days[point[0] * 7 + point[1]]["date"].encode("utf-8")).hexdigest(),
    )
    current = (max(0, columns // 2), 3)
    route = [current]
    for turn, target in enumerate(ordered):
        key = days[target[0] * 7 + target[1]]["date"]
        horizontal_first = (int(sha256(f"{key}:{turn}".encode("utf-8")).hexdigest()[:2], 16) % 2) == 0
        segment = grid_step_path(current, target, horizontal_first)
        route.extend(segment[1:])
        current = target
    return route, set(active_points), ordered


def contribution_snake_gif_frame(days: list[dict], frame_index: int, frame_total: int = 48) -> Image.Image:
    if not days:
        raise RuntimeError("No public contribution days are available for the contribution snake visual.")
    colors = {"bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "text": "#c9d1d9", "muted": "#8b949e", "empty": "#21262d", "level1": "#0e4429", "level2": "#006d32", "level3": "#26a641", "level4": "#39d353", "snake": "#39d353", "snake_alt": "#70e890", "head": "#a7f3b8", "eye": "#0d1117", "tongue": "#ff6b6b", "food": "#f85149", "leaf": "#3fb950"}
    width, height = 840, 230
    image = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=14, fill=colors["panel"], outline=colors["line"], width=2)
    draw.text((24, 20), "CONTRIBUTION SNAKE GAME", fill=colors["text"], font=font)
    draw.text((24, 39), "live active-cell snake game · slower varied-turn route", fill=colors["muted"], font=font)
    maximum = max(day["contributionCount"] for day in days) or 1
    cell, gap = 10, 3
    start_x, start_y = 26, 78
    columns = max(1, (len(days) + 6) // 7)
    board_right = start_x + columns * (cell + gap) - gap + 10
    board_bottom = start_y + 7 * (cell + gap) - gap + 10
    draw.rounded_rectangle((16, 66, board_right, board_bottom), radius=8, fill=colors["bg"], outline=colors["line"], width=1)
    route, active_points, target_order = active_cell_route(days, columns)
    body_length = 5
    first_head = min(body_length, len(route) - 1)
    head_index = first_head + int(frame_index * (len(route) - 1 - first_head) / max(1, frame_total - 1))
    visited = set(route[: head_index + 1])
    eaten = active_points.intersection(visited)
    next_target = next((point for point in target_order if point not in eaten), None)
    for index, day in enumerate(days):
        count = day["contributionCount"]
        level = 0 if count == 0 else min(4, max(1, round(count * 4 / maximum)))
        column, row = divmod(index, 7)
        point = (column, row)
        fill = colors["empty"] if level == 0 or point in eaten else colors[f"level{level}"]
        x, y = start_x + column * (cell + gap), start_y + row * (cell + gap)
        draw.rounded_rectangle((x, y, x + cell, y + cell), radius=2, fill=fill)
    if next_target:
        food_x = start_x + next_target[0] * (cell + gap) + cell // 2
        food_y = start_y + next_target[1] * (cell + gap) + cell // 2
        draw.ellipse((food_x - 4, food_y - 4, food_x + 4, food_y + 4), fill=colors["food"])
        draw.arc((food_x, food_y - 7, food_x + 7, food_y + 1), 190, 340, fill=colors["leaf"], width=1)
    body_indices = [max(0, head_index - offset) for offset in range(body_length, -1, -1)]
    body_points = [(start_x + route[index][0] * (cell + gap) + cell // 2, start_y + route[index][1] * (cell + gap) + cell // 2) for index in body_indices]
    if len(body_points) > 1:
        draw.line(body_points, fill=colors["snake_alt"], width=6, joint="curve")
        draw.line(body_points, fill=colors["snake"], width=3, joint="curve")
    for x, y in body_points[:-1]:
        draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=colors["snake"])
    head_x, head_y = body_points[-1]
    previous_x, previous_y = body_points[-2] if len(body_points) > 1 else (head_x - 1, head_y)
    direction_x, direction_y = head_x - previous_x, head_y - previous_y
    draw.ellipse((head_x - 4, head_y - 4, head_x + 4, head_y + 4), fill=colors["head"], outline=colors["bg"], width=1)
    if abs(direction_x) >= abs(direction_y):
        sign = 1 if direction_x >= 0 else -1
        draw.ellipse((head_x + sign, head_y - 2, head_x + sign + 1, head_y - 1), fill=colors["eye"])
        draw.ellipse((head_x + sign, head_y + 1, head_x + sign + 1, head_y + 2), fill=colors["eye"])
        draw.line((head_x + sign * 4, head_y, head_x + sign * 7, head_y - 1), fill=colors["tongue"], width=1)
    else:
        sign = 1 if direction_y >= 0 else -1
        draw.ellipse((head_x - 2, head_y + sign, head_x - 1, head_y + sign + 1), fill=colors["eye"])
        draw.ellipse((head_x + 1, head_y + sign, head_x + 2, head_y + sign + 1), fill=colors["eye"])
        draw.line((head_x, head_y + sign * 4, head_x + 1, head_y + sign * 7), fill=colors["tongue"], width=1)
    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    total = sum(day["contributionCount"] for day in days)
    draw.line((16, 194, width - 16, 194), fill=colors["line"], width=1)
    draw.text((24, 204), f"{active_days} active public days · {len(eaten)}/{len(active_points)} eaten · slower varied-turn path", fill=colors["muted"], font=font)
    return image


def render_contribution_snake(user: dict) -> str:
    days = contribution_days(user)
    version = contribution_version(days)
    os.makedirs("assets", exist_ok=True)
    frames = [contribution_snake_gif_frame(days, index) for index in range(48)]
    frames[0].save("assets/contribution-snake.gif", save_all=True, append_images=frames[1:], duration=190, loop=0, disposal=2, optimize=True)
    test_dir = os.environ.get("SNAKE_TEST_FRAMES_DIR")
    if test_dir:
        os.makedirs(test_dir, exist_ok=True)
        for index in (0, 12, 24, 36, 47):
            frames[index].save(os.path.join(test_dir, f"snake-state-{index:02d}.png"))
    return version


def event_summary(event: dict) -> str:
    event_type = event.get("type", "PublicEvent")
    repository = event.get("repo", {}).get("name", "a public repository")
    payload = event.get("payload") or {}
    action = payload.get("action")
    if event_type == "PushEvent":
        count = payload.get("distinct_size") or payload.get("size") or 0
        return f"Pushed {count} commit{'s' if count != 1 else ''} to `{repository}`" if count else f"Updated `{repository}`"
    if event_type == "CreateEvent":
        return f"Created {payload.get('ref_type', 'a source item')} in `{repository}`"
    if event_type == "PublicEvent":
        return f"Made `{repository}` public"
    if event_type == "WatchEvent":
        return f"Starred `{repository}`"
    if event_type == "ForkEvent":
        return f"Fork activity in `{repository}`"
    if event_type == "PullRequestEvent":
        return f"{(action or 'Updated').capitalize()} a pull request in `{repository}`"
    if event_type == "IssuesEvent":
        return f"{(action or 'Updated').capitalize()} an issue in `{repository}`"
    if event_type == "IssueCommentEvent":
        return f"Commented on an issue in `{repository}`"
    if event_type == "ReleaseEvent":
        return f"{(action or 'Updated').capitalize()} a release in `{repository}`"
    return f"{event_type.removesuffix('Event')} activity in `{repository}`"


def recent_activity(events: list[dict], limit: int = 4) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        date = format_date(event["created_at"])
        summary = event_summary(event)
        key = (date, summary)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{date}** — {summary}")
        if len(lines) == limit:
            break
    return lines or ["- No recent public event is currently available through GitHub’s public events feed."]


def latest_contribution_date(user: dict) -> str:
    days = [
        day for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
        if day["contributionCount"] > 0
    ]
    return format_date(max(days, key=lambda day: day["date"])["date"] + "T00:00:00Z") if days else "no contribution recorded"


def project_record(repository: dict, ordinal: int, is_pinned: bool, is_open: bool) -> list[str]:
    language = (repository.get("primaryLanguage") or {}).get("name") or "source"
    markers = [f"`{language}`", f"updated {format_date(repository['updatedAt'])}"]
    if is_pinned:
        markers.append("pinned")
    if repository.get("isArchived"):
        markers.append("archived")
    star_label = "star" if repository["stargazerCount"] == 1 else "stars"
    fork_label = "fork" if repository["forkCount"] == 1 else "forks"
    return [
        f"<details{' open' if is_open else ''}>",
        f"<summary><strong>{ordinal:02d} · {repository['name']}</strong> · {language} · updated {format_date(repository['updatedAt'])}</summary>",
        "",
        concise(repository.get("description")),
        "",
        f"{' · '.join(markers)} · {repository['stargazerCount']} {star_label} · {repository['forkCount']} {fork_label}",
        "",
        f"[Open source →]({repository['url']})",
        "",
        "</details>",
        "",
    ]


def build_readme(user: dict, repositories: list[dict], events: list[dict], contribution_snake_version: str) -> str:
    if not repositories:
        raise RuntimeError("No public non-profile repositories are available to synchronize.")
    pinned_names = {
        item["name"] for item in user["pinnedItems"]["nodes"]
        if item and item.get("name") in {repository["name"] for repository in repositories}
    }
    name = user.get("name") or user["login"]
    contribution_total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    total_stars = sum(repository["stargazerCount"] for repository in repositories)
    total_forks = sum(repository["forkCount"] for repository in repositories)
    newest = max(repositories, key=lambda repository: repository["updatedAt"])
    latest_event = event_summary(events[0]) if events else "No recent public event is currently available"
    latest_event_date = format_date(events[0]["created_at"]) if events else "—"

    lines = [
        f"# {name}",
        "",
        "<p align=\"center\">",
        "  <code>competitive programming</code> · <code>C / C++ / Java</code> · <code>Python Libraries</code> · <code>ONNX</code>",
        "</p>",
        "",
        f"{user.get('location') or 'GitHub'} · [@{user['login']}]({user['url']})",
        "",
        "> I use algorithmic practice to develop precision, build close-to-the-machine software in C and C++, and extend those foundations through Python data work and ONNX models.",
        "",
        "---",
        "",
        "## Live source heartbeat",
        "",
        "```text",
        f"PUBLIC REPOSITORIES  {user['repositories']['totalCount']}",
        f"SOURCE STARS         {total_stars}",
        f"SOURCE FORKS         {total_forks}",
        f"CONTRIBUTIONS        {contribution_total} in the last year",
        f"LAST CONTRIBUTION    {latest_contribution_date(user)}",
        f"LATEST SOURCE        {newest['name']} · {format_date(newest['updatedAt'])}",
        "```",
        "",
        *native_footprint(repositories),
        "",
        "---",
        "",
        "## Contribution snake tracker",
        "",
        f"<img src=\"https://raw.githubusercontent.com/{OWNER}/{OWNER}/main/assets/contribution-snake.gif?v={contribution_snake_version}\" alt=\"Tested animated snake-game tracker running across the public GitHub contribution chart.\">",
        "",
        "_A tested snake-game tracker crossing the public GitHub contribution chart. It refreshes with the scheduled profile sync._",
        "",
        "---",
        "",
        "## Public build records",
        "",
    ]
    for ordinal, repository in enumerate(repositories, start=1):
        lines.extend(project_record(repository, ordinal, repository["name"] in pinned_names, ordinal == 1))
    lines.extend(
        [
            "---",
            "",
            "## Latest GitHub trace",
            "",
            "```text",
            f"LATEST EVENT   {latest_event_date} · {latest_event.replace('`', '')}",
            "SYNC WINDOW    every 15 minutes",
            "```",
            "",
            *recent_activity(events),
            "",
            "---",
            "",
            "<sub>Live public data only: repository records, pins, source updates, language bytes, stars, forks, contributions, and activity refresh every 15 minutes. New public repositories appear after the next successful synchronization. The Coding Footprint is native text, never an image.</sub>",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print("Synchronizing public account and repository data…", flush=True)
    user = account_data()
    print("Synchronizing recent public activity…", flush=True)
    repositories = source_repositories(user)
    events = public_events()
    contribution_snake_version = render_contribution_snake(user)
    print("Writing builder dossier profile README…", flush=True)
    with open("README.md", "w", encoding="utf-8") as output:
        output.write(build_readme(user, repositories, events, contribution_snake_version))
    print("Builder dossier profile synchronization complete.", flush=True)
