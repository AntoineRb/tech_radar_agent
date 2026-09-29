from collections import Counter
from pathlib import Path

import pytest
import yaml

from tech_radar_agent.collectors import build_collector
from tech_radar_agent.config import load_config

REAL_CONFIG = Path(__file__).parents[1] / "config" / "interests.yaml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "interests.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_config(tmp_path):
    path = write(tmp_path, "profile:\n  about: me\nsources:\n  - type: hackernews\n    limit: 5\n")
    assert load_config(path) == {"profile": {"about": "me"}, "sources": [{"type": "hackernews", "limit": 5}]}


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "mapping at the top level"),
        ("- just\n- a list\n", "mapping at the top level"),
        ("profile: {}\n", "non-empty list"),
        ("sources: []\n", "non-empty list"),
        ("sources: hackernews\n", "non-empty list"),
        ("sources:\n  - hackernews\n", "must be a mapping"),
    ],
)
def test_invalid_shape(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        load_config(write(tmp_path, text))


def test_invalid_yaml(tmp_path):
    with pytest.raises(yaml.YAMLError):
        load_config(write(tmp_path, "sources: [unclosed\n"))


def test_python_objects_are_never_built(tmp_path):
    # yaml.load would run os.system here; yaml.safe_load must refuse the tag.
    marker = tmp_path / "pwned"
    path = write(tmp_path, f"sources: !!python/object/apply:os.system ['touch {marker}']\n")
    with pytest.raises(yaml.YAMLError):
        load_config(path)
    assert not marker.exists()


@pytest.fixture(scope="module")
def config():
    return load_config(REAL_CONFIG)


class TestRealConfig:
    """Guards config/interests.yaml itself: a broken edit fails here, not in tomorrow's run."""

    def test_profile_is_filled(self, config):
        profile = config["profile"]
        assert profile["about"].strip()
        assert any(profile["interests"].get(level) for level in ("high", "medium", "low"))

    def test_every_source_builds(self, config):
        for source in config["sources"]:
            build_collector(source)

    def test_source_names_are_unique(self, config):
        names = Counter(build_collector(source).name for source in config["sources"])
        assert [name for name, count in names.items() if count > 1] == []

    def test_feeds_use_https(self, config):
        urls = [source["url"] for source in config["sources"] if "url" in source]
        assert urls
        assert all(url.startswith("https://") for url in urls)
