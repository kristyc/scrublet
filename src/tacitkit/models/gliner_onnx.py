"""A lean runner for GLiNER multi PII v1 exported to ONNX: onnxruntime, tokenizers and numpy only.

No torch, no transformers, no gliner package. It reproduces what the gliner package does around
the ONNX graph, and the bench proves it (`tests` and `bench/results`): the same prediction on all
1,430 corpus cases.

How the model is fed (the gliner convention, one entity label here, "person"):

- words: `\\w+(?:[-_]\\w+)*|\\S` over the text, with character offsets;
- tokens: `[CLS] <<ENT>> person <<SEP>> word word ...` tokenised word by word (each word is its
  own pre-token), then `[SEP]`;
- `words_mask`: 1, 2, 3, ... on the first sub-token of each text word, 0 elsewhere;
- `text_lengths`: the number of text words;
- `span_idx`: every (start, start + k) for k in 0..max_width-1, `span_mask`: end < words;
- output logits: (1, words, max_width, labels); a span is a candidate when sigmoid(logit) is above
  the threshold, then non-overlapping spans are kept greedily by score (gliner's flat NER).

Unlike the gliner package, which silently drops everything past its first 384 words, a long text
is processed in overlapping windows, so no part of it goes unseen (this matters when the job is
hiding names).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WORD = re.compile(r"\w+(?:[-_]\w+)*|\S")
MAX_TOKENS = 500  # the encoder takes 512 positions; leave room for [CLS], [SEP] and the prompt
OVERLAP = 12  # words shared by neighbouring windows, so a name on a boundary is seen whole


class GlinerOnnx:
    """detect(text) -> [(start, stop), ...] for the labels given (default: person)."""

    def __init__(
        self,
        folder: Path | str,
        onnx_file: str = "model_emb8.onnx",
        labels: tuple[str, ...] = ("person",),
        threshold: float = 0.5,
        threads: int = 2,
    ) -> None:
        import numpy  # noqa: PLC0415
        import onnxruntime  # noqa: PLC0415
        from tokenizers import Tokenizer  # noqa: PLC0415

        folder = Path(folder)
        config = json.loads((folder / "gliner_config.json").read_text(encoding="utf-8"))
        self.np = numpy
        self.max_width = int(config["max_width"])
        self.threshold = threshold
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.prompt = []
        for label in labels:
            self.prompt += [config["ent_token"], label]
        self.prompt.append(config["sep_token"])
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
        self.session = onnxruntime.InferenceSession(
            str(folder / onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self.wanted = {item.name for item in self.session.get_inputs()}
        self.labels = len(labels)

    def detect(self, text: str) -> list[tuple[int, int]]:
        words = [(m.group(), m.start(), m.end()) for m in WORD.finditer(text)]
        spans: list[tuple[int, int]] = []
        for first, last in self._windows([w for w, _, _ in words]):
            for start, end in self._run([w for w, _, _ in words[first:last]]):
                spans.append((words[first + start][1], words[first + end][2]))
        return _merge(spans)

    def _windows(self, words: list[str]) -> list[tuple[int, int]]:
        """Word ranges that each fit the encoder; one range for any ordinary text."""
        if not words:
            return []
        pieces = [
            len(self.tokenizer.encode([w], is_pretokenized=True, add_special_tokens=False).ids)
            for w in words
        ]
        budget = MAX_TOKENS - len(self.tokenizer.encode(self.prompt, is_pretokenized=True).ids)
        windows, first = [], 0
        while True:
            last, used = first, 0
            while last < len(words) and used + pieces[last] <= budget:
                used += pieces[last]
                last += 1
            last = max(last, first + 1)  # a single huge word still goes through
            windows.append((first, last))
            if last >= len(words):
                return windows
            first = max(last - OVERLAP, first + 1)

    def _run(self, words: list[str]) -> list[tuple[int, int]]:
        """Word-index spans (inclusive) the model hides for these words."""
        np = self.np
        encoding = self.tokenizer.encode(self.prompt + words, is_pretokenized=True)
        ids, word_ids = encoding.ids, encoding.word_ids
        skip, seen = len(self.prompt), set()
        mask = np.zeros(len(ids), dtype=np.int64)
        for position, word in enumerate(word_ids):
            if word is not None and word >= skip and word not in seen:
                seen.add(word)
                mask[position] = word - skip + 1
        count, width = len(words), self.max_width
        starts = np.repeat(np.arange(count), width)
        ends = starts + np.tile(np.arange(width), count)
        feed = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
            "words_mask": mask[None, :],
            "text_lengths": np.array([[count]], dtype=np.int64),
            "span_idx": np.stack([starts, ends], axis=1)[None, :, :].astype(np.int64),
            "span_mask": (ends < count)[None, :],
        }
        logits = self.session.run(None, {k: v for k, v in feed.items() if k in self.wanted})[0]
        scores = 1.0 / (1.0 + np.exp(-logits.reshape(count * width, self.labels).max(axis=1)))
        picked = np.flatnonzero((scores > self.threshold) & (ends < count))
        chosen: list[tuple[int, int]] = []
        for index in sorted(picked.tolist(), key=lambda i: -scores[i]):  # stable: ties keep order
            span = (int(starts[index]), int(ends[index]))
            if all(span[0] > other[1] or other[0] > span[1] for other in chosen):
                chosen.append(span)
        return sorted(chosen)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for start, stop in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], stop))
        else:
            out.append((start, stop))
    return out
