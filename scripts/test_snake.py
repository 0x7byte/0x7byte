from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from sync_profile import build_readme, contribution_snake_gif_frame


def make_days():
    return [
        {"date": f"2026-01-{index + 1:02d}", "contributionCount": (index % 5) if index % 7 else 0}
        for index in range(28)
    ]


def test_frames_are_renderable_and_distinct():
    days = make_days()
    first = contribution_snake_gif_frame(days, 0)
    middle = contribution_snake_gif_frame(days, 24)
    assert first.size == middle.size
    assert first.mode == "RGB"
    assert first.tobytes() != middle.tobytes()


def test_empty_calendar_still_renders():
    days = [{"date": f"2026-02-{index + 1:02d}", "contributionCount": 0} for index in range(14)]
    frame = contribution_snake_gif_frame(days, 0)
    assert isinstance(frame, Image.Image)
    assert frame.width > 0 and frame.height > 0


def test_readme_uses_committed_gif():
    user = {
        "name": "Test User",
        "login": "test-user",
        "url": "https://github.com/test-user",
        "location": "Test",
        "repositories": {"totalCount": 1},
        "contributionsCollection": {
            "contributionCalendar": {
                "totalContributions": 1,
                "weeks": [{"contributionDays": [{"date": "2026-01-01", "contributionCount": 1}]}],
            }
        },
        "pinnedItems": {"nodes": []},
    }
    repositories = [{
        "name": "demo",
        "description": "Demo",
        "updatedAt": "2026-01-01T00:00:00Z",
        "stargazerCount": 0,
        "forkCount": 0,
        "url": "https://github.com/test-user/demo",
        "primaryLanguage": {"name": "Python", "color": "#3572A5"},
        "languages": {"edges": [{"size": 1, "node": {"name": "Python", "color": "#3572A5"}}]},
    }]
    readme = build_readme(user, repositories, [], "test-version")
    assert "main/assets/contribution-snake.gif?v=test-version" in readme
    assert "output/github-snake.svg" not in readme


if __name__ == "__main__":
    test_frames_are_renderable_and_distinct()
    test_empty_calendar_still_renders()
    test_readme_uses_committed_gif()
    print("snake regression tests passed")
