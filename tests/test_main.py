import logging
import sqlite3
from pathlib import Path

import pytest

from tech_radar_agent import EXIT_ALL_SOURCES_FAILED, EXIT_CONFIG_ERROR, EXIT_OK, main
from tech_radar_agent.collectors import COLLECTOR_TYPES, Collector
from tech_radar_agent.models import Article

DB_PATH = Path("data/tech_radar.db")


class FakeCollector(Collector):
    """Returns `count` articles, or raises if `fail` is set. No network involved."""

    type = "fake"

    def __init__(self, name: str | None = None, count: int = 1, fail: bool = False) -> None:
        super().__init__(name)
        self.count = count
        self.fail = fail

    def collect(self) -> list[Article]:
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return [
            Article(source=self.name, title=f"{self.name} {i}", url=f"https://example.com/{self.name}/{i}")
            for i in range(self.count)
        ]


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch, caplog):
    """Run main() in an empty folder (it uses paths relative to the working directory)."""
    caplog.set_level(logging.INFO)  # pytest's handlers make main()'s basicConfig a no-op.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    monkeypatch.setitem(COLLECTOR_TYPES, "fake", FakeCollector)


def run(config: str) -> int:
    Path("config/interests.yaml").write_text(config, encoding="utf-8")
    return main()


def stored_sources() -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        return [row[0] for row in conn.execute("SELECT source FROM articles ORDER BY id")]


def test_articles_from_every_source_are_saved():
    config = "sources:\n  - {type: fake, name: a, count: 2}\n  - {type: fake, name: b, count: 1}\n"
    assert run(config) == EXIT_OK
    assert stored_sources() == ["a", "a", "b"]


def test_second_run_adds_nothing(caplog):
    config = "sources:\n  - {type: fake, name: a, count: 2}\n"
    run(config)
    assert run(config) == EXIT_OK
    assert len(stored_sources()) == 2
    assert "0 new" in caplog.text


def test_failing_source_does_not_stop_the_others(caplog):
    config = (
        "sources:\n"
        "  - {type: fake, name: before}\n"
        "  - {type: fake, name: broken, fail: true}\n"
        "  - {type: fake, name: after}\n"
    )
    assert run(config) == EXIT_OK
    assert stored_sources() == ["before", "after"]
    assert "broken: source failed" in caplog.text
    assert "1/3 sources failed (broken)" in caplog.text


def test_all_sources_failing():
    config = "sources:\n  - {type: fake, name: x, fail: true}\n  - {type: fake, name: y, fail: true}\n"
    assert run(config) == EXIT_ALL_SOURCES_FAILED


def test_source_with_no_articles_is_not_a_failure():
    assert run("sources:\n  - {type: fake, count: 0}\n") == EXIT_OK


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("sources:\n  - {type: fake}\n  - {type: fake}\n", id="duplicate-names"),
        pytest.param("sources:\n  - {type: twitter}\n", id="unknown-type"),
        pytest.param("sources:\n  - {type: fake, countt: 3}\n", id="misspelled-option"),
        pytest.param("profile: {}\n", id="no-sources"),
        pytest.param("sources: [unclosed\n", id="invalid-yaml"),
        pytest.param("sources: !!python/object/apply:os.system ['echo PWNED']\n", id="unsafe-yaml"),
    ],
)
def test_config_errors_stop_before_collecting(config, caplog):
    assert run(config) == EXIT_CONFIG_ERROR
    assert "Invalid configuration" in caplog.text
    assert not DB_PATH.parent.exists()  # Stopped before opening the database.


def test_missing_config_file():
    assert main() == EXIT_CONFIG_ERROR


def test_one_bad_entry_stops_everything():
    # Even valid sources are not run: config errors must be fixed, not skipped.
    assert run("sources:\n  - {type: fake, name: ok}\n  - {type: twitter}\n") == EXIT_CONFIG_ERROR
    assert not DB_PATH.exists()
