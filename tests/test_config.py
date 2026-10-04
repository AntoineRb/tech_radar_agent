from collections import Counter
from pathlib import Path

import pytest
import yaml

from tech_radar_agent.collectors import build_collector
from tech_radar_agent.config import DEFAULT_LANGUAGE, Interest, load_config, parse_profile

REAL_CONFIG = Path(__file__).parents[1] / "config" / "interests.yaml"

PROFILE = """
profile:
  about: >
    Python developer
    building agents.
  language: French
  interests:
    high:
      ai-agents: AI agents (tool use, memory)
      python: Python
    low:
      open-source: Open source projects
  not_interested:
    - Crypto
"""
SOURCES = "sources:\n  - type: hackernews\n    limit: 5\n"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "interests.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def profile_from(text: str):
    """Parse the `profile:` part of a YAML snippet."""
    return parse_profile(yaml.safe_load(text)["profile"])


# --- Whole file ---


def test_valid_config(tmp_path):
    config = load_config(write(tmp_path, PROFILE + SOURCES))
    assert config.sources == [{"type": "hackernews", "limit": 5}]
    assert config.profile.language == "French"


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "mapping at the top level"),
        ("- just\n- a list\n", "mapping at the top level"),
        (PROFILE, "non-empty list"),
        (PROFILE + "sources: []\n", "non-empty list"),
        (PROFILE + "sources: hackernews\n", "non-empty list"),
        (PROFILE + "sources:\n  - hackernews\n", "must be a mapping"),
        (SOURCES, "`profile` must be a mapping"),
    ],
)
def test_invalid_shape(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        load_config(write(tmp_path, text))


def test_errors_name_the_file(tmp_path):
    path = write(tmp_path, SOURCES)
    with pytest.raises(ValueError, match="interests.yaml"):
        load_config(path)


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


# --- Profile ---


class TestProfile:
    def test_fields(self):
        profile = profile_from(PROFILE)
        assert profile.about == "Python developer building agents."  # Folded text, single spaces.
        assert profile.language == "French"
        assert profile.not_interested == ("Crypto",)

    def test_interests_keep_id_description_and_priority(self):
        assert profile_from(PROFILE).interests == (
            Interest("ai-agents", "AI agents (tool use, memory)", "high"),
            Interest("python", "Python", "high"),
            Interest("open-source", "Open source projects", "low"),
        )

    def test_interests_are_sorted_by_priority(self):
        text = "profile:\n  about: me\n  interests:\n    low:\n      b: B\n    high:\n      a: A\n"
        assert [i.id for i in profile_from(text).interests] == ["a", "b"]

    def test_interest_ids(self):
        assert profile_from(PROFILE).interest_ids == {"ai-agents", "python", "open-source"}

    def test_optional_fields_have_defaults(self):
        profile = profile_from("profile:\n  about: me\n  interests:\n    high:\n      python: Python\n")
        assert profile.language == DEFAULT_LANGUAGE
        assert profile.not_interested == ()

    def test_empty_priority_is_allowed(self):
        text = "profile:\n  about: me\n  interests:\n    high:\n      python: Python\n    low:\n"
        assert len(profile_from(text).interests) == 1


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        pytest.param({"interests": {"high": {"a": "A"}}}, "profile.about", id="no-about"),
        pytest.param({"about": "  ", "interests": {"high": {"a": "A"}}}, "profile.about", id="blank-about"),
        pytest.param({"about": "me", "language": "", "interests": {"high": {"a": "A"}}}, "profile.language", id="blank-language"),
        pytest.param({"about": "me", "language": 3, "interests": {"high": {"a": "A"}}}, "profile.language", id="language-not-text"),
        pytest.param({"about": "me"}, "profile.interests", id="no-interests"),
        pytest.param({"about": "me", "interests": {}}, "at least one interest", id="empty-interests"),
        pytest.param({"about": "me", "interests": {"high": None}}, "at least one interest", id="only-empty-priorities"),
        pytest.param({"about": "me", "interests": ["python"]}, "profile.interests", id="interests-as-list"),
        pytest.param({"about": "me", "interests": {"urgent": {"a": "A"}}}, "unknown priorities", id="unknown-priority"),
        pytest.param({"about": "me", "interests": {"high": ["Python"]}}, "map ids to descriptions", id="old-list-format"),
        pytest.param({"about": "me", "interests": {"high": {"a": "A"}, "low": {"a": "B"}}}, "used twice", id="duplicate-id"),
        pytest.param({"about": "me", "interests": {"high": {"a": ""}}}, "interest 'a'", id="blank-description"),
        pytest.param({"about": "me", "interests": {"high": {"a": "A"}}, "not_interested": "Crypto"}, "not_interested", id="not-interested-not-a-list"),
    ],
)
def test_invalid_profile(profile, message):
    with pytest.raises(ValueError, match=message):
        parse_profile(profile)


@pytest.mark.parametrize("interest_id", ["AI-agents", "ai agents", "ai_agents", "-python", "python-", "py--thon", "", "é"])
def test_invalid_interest_id(interest_id):
    with pytest.raises(ValueError, match="invalid interest id"):
        parse_profile({"about": "me", "interests": {"high": {interest_id: "Description"}}})


def test_yaml_turns_some_keys_into_non_text(tmp_path):
    # In YAML, `2024:` is a number and `yes:` a boolean: both must be refused as ids, not crash.
    for key in ("2024", "yes"):
        text = f"profile:\n  about: me\n  interests:\n    high:\n      {key}: Something\n" + SOURCES
        with pytest.raises(ValueError, match="invalid interest id"):
            load_config(write(tmp_path, text))


# --- The real config/interests.yaml ---


@pytest.fixture(scope="module")
def config():
    return load_config(REAL_CONFIG)


class TestRealConfig:
    """Guards config/interests.yaml itself: a broken edit fails here, not in tomorrow's run."""

    def test_profile_is_filled(self, config):
        assert config.profile.about
        assert config.profile.language
        assert config.profile.interests

    def test_interest_list_stays_short(self, config):
        # A long list makes the prompt longer and the model less focused (see docs/configuration.md).
        assert len(config.profile.interests) <= 15

    def test_every_source_builds(self, config):
        for source in config.sources:
            build_collector(source)

    def test_source_names_are_unique(self, config):
        names = Counter(build_collector(source).name for source in config.sources)
        assert [name for name, count in names.items() if count > 1] == []

    def test_feeds_use_https(self, config):
        urls = [source["url"] for source in config.sources if "url" in source]
        assert urls
        assert all(url.startswith("https://") for url in urls)
