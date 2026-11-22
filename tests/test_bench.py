"""The bench module: a sound corpus, honest statistics, declared licences, a report that states
its rule first, stored results without personal data, and downloads cleaned up by default."""

import json
import re
from pathlib import Path

import pytest

from scrublet_pii.bench import adapters, cases, cli, report, results, stats, worker

CORPUS = cases.build()
FACTS = (*cases.FACT_CATS, cases.AMBIGUOUS)


def test_the_corpus_is_1430_cases_in_13_categories_of_110_and_always_the_same():
    assert len(CORPUS) == 1430
    counts = {}
    for case in CORPUS:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    assert len(counts) == 13 and set(counts.values()) == {110}
    assert cases.build() == CORPUS
    assert cases.corpus_hash(CORPUS) == "a3c5dd3dfeec8a34"


def test_every_name_and_fact_sits_in_its_text_and_the_ids_are_unique():
    assert len({c["id"] for c in CORPUS}) == len(CORPUS)
    for case in CORPUS:
        for item in (*case["names"], *case["keeps"]):
            assert item in case["text"]


def test_the_corpus_holds_no_real_looking_account_or_id_numbers():
    # amounts, dates and a reference are the only digits; no 12-digit IC or 16-digit card
    for case in CORPUS:
        assert not re.search(r"\d{12}", case["text"]), case["text"]
        assert not re.search(r"\b\d{6}-\d{2}-\d{4}\b", case["text"])


def test_a_name_is_caught_when_every_word_is_hidden_and_markers_may_stay():
    case = {"text": "Call Ahmad bin Ismail now", "names": ["Ahmad bin Ismail"], "keeps": ["now"]}
    assert stats.judge(case, [(5, 10), (15, 21)]) == (True, [False])  # Ahmad and Ismail
    assert stats.judge(case, [(5, 10)]) == (False, [False])  # Ismail missed
    assert stats.judge(case, [(5, 21), (22, 25)]) == (True, [True])  # also hid the fact


def test_half_a_word_counts_as_hidden_and_less_does_not():
    case = {"text": "Tell Alexander now", "names": ["Alexander"], "keeps": []}
    assert stats.judge(case, [(5, 9)])[0] is False  # 4 of 9 letters
    assert stats.judge(case, [(5, 10)])[0] is True  # 5 of 9


def test_the_wilson_interval_and_the_exact_mcnemar_test_match_known_values():
    low, high = stats.wilson(50, 100)
    assert 40 < low < 41 and 59 < high < 60
    assert stats.wilson(0, 0) == (0.0, 0.0)
    assert stats.mcnemar([True] * 10, [False] * 10) == pytest.approx(2 / 1024)
    assert stats.mcnemar([True, False], [True, False]) == 1.0
    assert (
        stats.mcnemar([True] * 5 + [False] * 5, [False] * 5 + [True] * 5) == 1.0
    )  # a tie is noise


def run_of(truth, fast_ms=1.0, ram=100.0):
    """A worker result for a finder that is right on every name (or finds nothing)."""
    spans = {
        str(c["id"]): (
            [[c["text"].index(n), c["text"].index(n) + len(n)] for n in c["names"]] if truth else []
        )
        for c in CORPUS
    }
    return {"spans": spans, "ms": [fast_ms] * len(CORPUS), "ram_peak_mb": ram, "ram_load_mb": ram}


def scored(truth, **kw):
    return stats.score(
        CORPUS,
        run_of(truth, **kw),
        cases.NAME_CATS,
        cases.FACT_CATS,
        cases.ASIAN_CATS,
        cases.AMBIGUOUS,
    )


def test_a_perfect_finder_scores_100_and_a_null_finder_0_and_neither_hides_a_fact():
    perfect, null = scored(True), scored(False)
    assert perfect.caught == perfect.asian == 100 and null.caught == 0
    assert perfect.hidden == null.hidden == 0
    assert perfect.n_names == 110 * 8 + 53 and perfect.n_facts > 1000


def specs():
    return [adapters.SPECS["null"], adapters.SPECS["oracle"]]


def test_the_rule_is_stated_and_a_model_must_pass_every_part():
    rule = report.Rule(min_gain_points=10, max_ram_mb=500, max_p95_ms=50)
    assert len(rule.describe()) == 3
    rows = report.evaluate(specs(), {"null": scored(False), "oracle": scored(True)}, "null", rule)
    assert rows[1].adopted and not rows[0].adopted
    slow = report.evaluate(
        specs(), {"null": scored(False), "oracle": scored(True, fast_ms=80)}, "null", rule
    )
    assert not slow[1].adopted and slow[1].passes["p95_speed"] is False


def test_the_report_states_the_rule_first_flags_noise_and_names_the_closest_when_none_passes():
    rule = report.Rule(min_gain_points=10, max_ram_mb=50)
    rows = report.evaluate(specs(), {"null": scored(False), "oracle": scored(True)}, "null", rule)
    info = {"hash": "x", "n": 1430, "categories": 13}
    text = report.markdown("T", "2026-11-22", rows, "null", rule, info, 2)
    assert text.index("Decision rule") < text.index("Recommendation") < text.index("Headline")
    assert (
        "No model passes every rule" in text
        and "fails peak RAM" not in text
        and "fails ram" in text
    )
    assert "within noise" in text  # the oracle hides the same facts as the null finder: 0 vs 0


def test_the_record_carries_every_field_the_history_needs_and_no_case_text():
    rule = report.Rule(max_ram_mb=500)
    rows = report.evaluate(specs(), {"null": scored(False), "oracle": scored(True)}, "null", rule)
    record = report.result_json(
        "T", rows, "null", rule, {"hash": "x", "n": 1430, "categories": 13}, 2, {}
    )
    model = record["models"][1]
    assert {
        "model",
        "revision",
        "precision",
        "licence",
        "ram_peak_mb",
        "ms_median",
        "ms_p95",
        "per_category",
        "names_caught_pct",
        "wrongly_hidden_pct",
        "adopted",
    } <= set(model)
    assert record["winner"] == "oracle" and record["decision"] == "adopt oracle"
    dumped = json.dumps(record)
    assert not any(c["text"] in dumped for c in CORPUS[:200])


def test_every_adapter_declares_its_licence_and_what_it_means_and_pins_a_commit():
    for spec in adapters.SPECS.values():
        assert spec.licence and spec.consequence, spec.name
        if spec.repo:
            assert re.fullmatch(r"[0-9a-f]{40}", spec.revision), spec.name
    for name in ("deberta_ai4privacy", "piiranha"):
        assert "can't be bundled" in adapters.SPECS[name].consequence
    assert "unmodified" in adapters.SPECS["piiranha"].consequence


def test_no_model_weights_are_in_the_repo():
    root = Path(__file__).resolve().parents[1]
    heavy = [
        p
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts and p.stat().st_size > 5_000_000
    ]
    assert heavy == []


def test_results_append_never_overwrite_and_the_index_lists_every_run(tmp_path):
    rule = report.Rule(max_ram_mb=500)
    rows = report.evaluate(specs(), {"null": scored(False), "oracle": scored(True)}, "null", rule)
    record = report.result_json(
        "T",
        rows,
        "null",
        rule,
        {"hash": "x", "n": 1430, "categories": 13},
        2,
        {},
        date="2026-11-22",
    )
    first = results.save(tmp_path, {**record, "name": "My Run"}, "report one")
    second = results.save(tmp_path, {**record, "name": "My Run"}, "report two")
    assert first.name == "2026-11-22-my-run.md" and second.name == "2026-11-22-my-run-2.md"
    assert first.read_text() == "report one"
    lines = (tmp_path / "README.md").read_text().splitlines()
    assert sum(1 for line in lines if line.startswith("| 2026-11-22")) == 2


def test_cleanup_removes_only_what_the_run_added(tmp_path):
    cache = tmp_path / "models"
    (cache / "hub" / "models--old--kept").mkdir(parents=True)
    (cache / "notes.txt").write_text("mine")
    before, hub_before = cli.listing(cache), cli.hub_listing(cache)
    (cache / "hub" / "models--new--model").mkdir()
    (cache / "xet").mkdir()
    removed = cli.cleanup(cache, before, hub_before, existed=True)
    assert len(removed) == 2
    assert (cache / "hub" / "models--old--kept").is_dir() and (
        cache / "notes.txt"
    ).read_text() == "mine"
    assert not (cache / "xet").exists() and not (cache / "hub" / "models--new--model").exists()


def test_cleanup_removes_a_cache_folder_it_created_and_refuses_a_drive_root_or_home(tmp_path):
    cache = tmp_path / "fresh"
    cache.mkdir()
    (cache / "hub").mkdir()
    (cache / "hub" / "models--a--b").mkdir()
    cli.cleanup(cache, set(), set(), existed=False)
    assert not cache.exists()
    for bad in (Path(Path.home().anchor), Path.home()):
        with pytest.raises(SystemExit):
            cli.safe_cache(str(bad))


def test_the_command_line_runs_fresh_processes_stores_the_result_and_removes_the_cache(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    src = str(Path(__file__).resolve().parents[1] / "src")
    monkeypatch.setenv("PYTHONPATH", src)
    cache = tmp_path / "weights"
    code = cli.main(
        [
            "bakeoff",
            "--models",
            "oracle,null",
            "--baseline",
            "null",
            "--cache",
            str(cache),
            "--rule",
            "none",
            "--threads",
            "1",
            "--out",
            str(tmp_path / "r.md"),
            "--name",
            "t",
        ]
    )
    assert code == 0 and not cache.exists()
    assert "Oracle" in (tmp_path / "r.md").read_text(encoding="utf-8")
    (stored,) = list((tmp_path / "bench" / "results").glob("*.json"))
    record = json.loads(stored.read_text())
    assert record["models"][1]["ram_peak_mb"] > 0 and record["corpus"]["hash"] == "a3c5dd3dfeec8a34"
    assert (tmp_path / "bench" / "results" / "README.md").is_file()


def test_the_worker_reports_memory_in_megabytes():
    current, peak = worker.memory_mb()
    assert 5 < current <= peak < 100_000
