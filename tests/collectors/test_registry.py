import pytest

from tech_radar_agent.collectors import (
    COLLECTOR_TYPES,
    GitHubCollector,
    HackerNewsCollector,
    RssCollector,
    build_collector,
)


def test_every_collector_is_registered_under_its_type():
    assert COLLECTOR_TYPES == {
        "github": GitHubCollector,
        "hackernews": HackerNewsCollector,
        "rss": RssCollector,
    }


def test_options_are_passed_to_the_constructor():
    collector = build_collector({"type": "hackernews", "name": "hn-best", "feed": "best", "limit": 5})
    assert isinstance(collector, HackerNewsCollector)
    assert (collector.name, collector.feed, collector.limit) == ("hn-best", "best", 5)


def test_config_entry_is_not_modified():
    source = {"type": "hackernews", "limit": 5}
    build_collector(source)
    assert source == {"type": "hackernews", "limit": 5}


@pytest.mark.parametrize("source", [{"type": "twitter"}, {"limit": 5}, {}])
def test_unknown_or_missing_type(source):
    with pytest.raises(ValueError, match="Unknown source type"):
        build_collector(source)


def test_misspelled_option():
    with pytest.raises(TypeError, match="limitt"):
        build_collector({"type": "hackernews", "limitt": 5})


def test_missing_required_option():
    with pytest.raises(TypeError, match="url"):
        build_collector({"type": "rss"})
