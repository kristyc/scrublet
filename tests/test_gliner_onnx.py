"""The lean GLiNER runner: its text handling is tested without a model; with the ONNX files in
SCRUBLET_GLINER_ONNX_DIR (the folder `export-gliner` makes) it is also run for real. The proof
that it matches the gliner package on all 1,430 corpus cases is a stored bench run
(bench/results/2026-11-22-lean-parity.md)."""

import itertools
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrublet_pii.models import gliner_onnx
from scrublet_pii.models.gliner_onnx import MAX_TOKENS, OVERLAP, GlinerOnnx

FOLDER = os.environ.get("SCRUBLET_GLINER_ONNX_DIR", "")


class Pieces:
    """A stand-in tokenizer: every word is `size` tokens, plus the prompt."""

    def __init__(self, size=1):
        self.size = size

    def encode(self, words, is_pretokenized=True, add_special_tokens=True):
        return SimpleNamespace(
            ids=[0] * (self.size * len(words) + (2 if add_special_tokens else 0))
        )


def runner(size=1):
    run = object.__new__(GlinerOnnx)
    run.tokenizer, run.prompt = Pieces(size), ["<<ENT>>", "person", "<<SEP>>"]
    return run


def test_importing_the_runner_loads_no_heavy_package():
    code = (
        "import sys; import scrublet_pii.models.gliner_onnx; "
        "heavy = ('torch', 'transformers', 'gliner', 'numpy', 'onnxruntime'); "
        "print(sorted(m for m in heavy if m in sys.modules))"
    )
    src = str(Path(__file__).resolve().parents[1] / "src")
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": src},
    )
    assert done.stdout.strip() == "[]"


def test_words_are_split_as_the_gliner_package_splits_them():
    words = [m.group() for m in gliner_onnx.WORD.finditer("Ahmad bin-Ismail, a/l K_R: 3.5!")]
    assert words == ["Ahmad", "bin-Ismail", ",", "a", "/", "l", "K_R", ":", "3", ".", "5", "!"]


def test_an_ordinary_text_is_one_window_and_an_empty_one_has_none():
    assert runner()._windows(["call", "Ahmad", "now"]) == [(0, 3)]
    assert runner()._windows([]) == []


def test_a_long_text_is_covered_by_overlapping_windows_that_each_fit_the_encoder():
    words = [f"w{n}" for n in range(1500)]
    windows = runner()._windows(words)
    assert windows[0][0] == 0 and windows[-1][1] == 1500 and len(windows) > 2
    for (first, last), (next_first, _) in itertools.pairwise(windows):
        assert last - first <= MAX_TOKENS and next_first == last - OVERLAP
    assert all(last - first <= MAX_TOKENS for first, last in windows)


def test_a_word_too_big_for_a_window_still_goes_through_alone():
    windows = runner(size=MAX_TOKENS + 5)._windows(["huge", "word"])
    assert windows[0] == (0, 1) and windows[-1][1] == 2


def test_spans_from_overlapping_windows_merge_into_one():
    assert gliner_onnx._merge([(18, 34), (30, 40), (50, 55), (5, 9)]) == [
        (5, 9),
        (18, 40),
        (50, 55),
    ]


@pytest.mark.skipif(
    not FOLDER, reason="SCRUBLET_GLINER_ONNX_DIR not set (needs the exported ONNX files)"
)
def test_with_the_real_model_it_finds_names_in_four_scripts_and_nothing_in_plain_text():
    model = GlinerOnnx(FOLDER)
    text = "Remind me to call Ahmad bin Ismail tomorrow, Lim Wei Ling too."
    assert [text[a:b] for a, b in model.detect(text)] == ["Ahmad bin Ismail", "Lim Wei Ling"]
    assert model.detect("") == [] and model.detect("!!! ???") == []
    assert model.detect("Pay the Tealive invoice before the 25th") == []
    hanzi = "张国伟 will send the signed form by Friday."
    assert [hanzi[a:b] for a, b in model.detect(hanzi)] == ["张国伟"]
    long = (
        "Ahmad bin Ismail opened. "
        + "the report covers costs " * 150
        + "Finally Rajesh a/l Krishnan left."
    )
    assert "Rajesh a/l Krishnan" in [long[a:b] for a, b in model.detect(long)]
