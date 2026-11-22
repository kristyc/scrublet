"""Model adapters: how to load a person-name finder and what its licence means.

An adapter is a `Spec` (what, where from, which precision, what the licence means in plain
words) plus a loader that turns it into `detect(text) -> [(start, stop), ...]`. No model
weights live in this repo. Weights download to a cache folder the user chooses, at the pinned
commit, and are removed after the run unless `--keep-models` is given. Third-party packages
(torch, gliner, onnxruntime, presidio, spaCy) are optional extras imported only by the
adapter that needs them, so `import tacitkit.bench` stays dependency-free.

Built-ins `oracle` and `null` need nothing and exist for tests and for smoke-checking the
harness (a perfect finder and one that finds nothing).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Detect = Callable[[str], list[tuple[int, int]]]

OK_OWN = "OK for personal and company use; can be bundled"
NON_COMMERCIAL = (
    "OK for her own, non-commercial projects; can't be bundled in a public library "
    "(it would be an optional download the user enables)"
)


@dataclass(frozen=True)
class Spec:
    name: str
    label: str
    kind: str  # oracle | null | onnx_ner | hf_tagger | gliner | gliner_onnx | presidio
    precision: str  # fp32 | int8 | fp32+emb8 ... (what the speed is for)
    licence: str
    consequence: str  # plain words for a product owner
    languages: str
    repo: str = ""
    revision: str = ""
    files: tuple[str, ...] = ()  # allow-list of files to download (keeps the cache small)
    options: dict = field(default_factory=dict, hash=False)
    extras: str = ""  # pip hint for the optional packages
    disk_mb: int = 0
    baseline_for: str = ""  # "int8"/"fp32": the reference row at that precision


GLINER_PII, GLINER_REV = "urchade/gliner_multi_pii-v1", "1fcf13e85f4eef5394e1fcd406cf2ca9ea82351d"
ONNX_DIR = "gliner_multi_pii-onnx"  # inside the cache, made by `tacitkit.bench export-gliner`


def _tagger(name, label, repo, revision, labels, licence, consequence, languages, mb, files):
    return Spec(
        name,
        label,
        "hf_tagger",
        "fp32",
        licence,
        consequence,
        languages,
        repo,
        revision,
        files,
        {"labels": sorted(labels)},
        "torch transformers",
        mb,
    )


SPECS: dict[str, Spec] = {
    s.name: s
    for s in [
        Spec("oracle", "Oracle (perfect, for tests)", "oracle", "n/a", "n/a", "Test double", "all"),
        Spec("null", "Null (finds nothing, for tests)", "null", "n/a", "n/a", "Test double", "all"),
        Spec(
            "current_ner",
            "bert-base-NER (int8 ONNX)",
            "onnx_ner",
            "int8",
            "MIT",
            "OK for personal and company use; can be bundled (the default name model today)",
            "English",
            "Xenova/bert-base-NER",
            "8e892123e8b7c2c0c2bd1dcb598b7d244c4e53aa",
            ("onnx/model_int8.onnx", "tokenizer.json", "config.json"),
            {"onnx_file": "onnx/model_int8.onnx"},
            "onnxruntime tokenizers",
            106,
            "int8",
        ),
        Spec(
            "current_ner_fp32",
            "bert-base-NER (fp32 ONNX)",
            "onnx_ner",
            "fp32",
            "MIT",
            "OK for personal and company use; can be bundled",
            "English",
            "Xenova/bert-base-NER",
            "8e892123e8b7c2c0c2bd1dcb598b7d244c4e53aa",
            ("onnx/model.onnx", "tokenizer.json", "config.json"),
            {"onnx_file": "onnx/model.onnx"},
            "onnxruntime tokenizers",
            411,
            "fp32",
        ),
        Spec(
            "presidio",
            "Presidio + spaCy en_core_web_lg",
            "presidio",
            "fp32",
            "MIT (Presidio, spaCy model)",
            "OK for personal and company use; can be bundled",
            "English",
            "",
            "",
            (),
            {},
            "presidio-analyzer spacy en_core_web_lg (download the spaCy model yourself)",
            425,
        ),
        Spec(
            "gliner_multi_pii",
            "GLiNER multi PII v1 (urchade, torch)",
            "gliner",
            "fp32",
            "Apache-2.0",
            OK_OWN,
            "6 European languages (handled Malay, Chinese and Tamil names well in tests)",
            GLINER_PII,
            GLINER_REV,
            ("*.json", "pytorch_model.bin"),
            {"labels": ["person"], "threshold": 0.5},
            "torch transformers gliner",
            1106,
        ),
        Spec(
            "gliner_multi_v21",
            "GLiNER multi v2.1 (urchade, torch)",
            "gliner",
            "fp32",
            "Apache-2.0",
            OK_OWN,
            "multilingual",
            "urchade/gliner_multi-v2.1",
            "443d26d654e0324125a96bebd8e796c14ff2efe6",
            ("*.json", "model.safetensors"),
            {"labels": ["person"], "threshold": 0.5},
            "torch transformers gliner",
            1106,
        ),
        Spec(
            "gliner_knowledgator",
            "GLiNER PII base (knowledgator, torch)",
            "gliner",
            "fp32",
            "Apache-2.0",
            OK_OWN,
            "English",
            "knowledgator/gliner-pii-base-v1.0",
            "61726e0ad791dcab3e29339bbec3ad42ded65641",
            ("*.json", "pytorch_model.bin", "spm.model"),
            {"labels": ["name", "first name", "last name"], "threshold": 0.3},
            "torch transformers gliner",
            644,
        ),
        Spec(
            "gliner_nvidia",
            "GLiNER-PII (NVIDIA, torch)",
            "gliner",
            "fp32",
            "NVIDIA Open Model License",
            "OK for her own use; bundling needs the licence text and NVIDIA's notice, and the licence "
            "ends if its safety guardrails are bypassed",
            "English",
            "nvidia/gliner-PII",
            "bd23e8ef4425fd04e34c5204ab49ffaa706eae79",
            ("*.json", "spm.model", "pytorch_model.bin"),
            {"labels": ["first_name", "last_name", "name"], "threshold": 0.3},
            "torch transformers gliner",
            1710,
        ),
        _tagger(
            "deberta_h2oai",
            "DeBERTa PII (h2oai)",
            "h2oai/deberta_finetuned_pii",
            "68089cd67db0b937a48ef97b62673cfdde67cb83",
            {"ACCOUNTNAME", "NAME", "FIRSTNAME", "LASTNAME", "MIDDLENAME", "FULLNAME"},
            "MIT (training data not stated)",
            "OK for personal and company use; the licence allows bundling but the data source is unknown",
            "English",
            532,
            (
                "config.json",
                "tokenizer*.json",
                "special_tokens_map.json",
                "added_tokens.json",
                "vocab.json",
                "merges.txt",
                "model.safetensors",
            ),
        ),
        _tagger(
            "deberta_ai4privacy",
            "DeBERTa-v3 ai4privacy v2 (Isotonic)",
            "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2",
            "9814d1113e03f72e8d383423188a51b43d5534c9",
            {"FIRSTNAME", "LASTNAME", "MIDDLENAME", "ACCOUNTNAME"},
            "CC-BY-NC-4.0 (non-commercial)",
            NON_COMMERCIAL,
            "English",
            712,
            (
                "config.json",
                "added_tokens.json",
                "special_tokens_map.json",
                "tokenizer*.json",
                "spm.model",
                "model.safetensors",
            ),
        ),
        _tagger(
            "piiranha",
            "Piiranha v1 (mDeBERTa)",
            "iiiorg/piiranha-v1-detect-personal-information",
            "255acde67a2f34cf452eb42e365b24d2957352fc",
            {"GIVENNAME", "SURNAME"},
            "CC-BY-NC-ND-4.0 (non-commercial, no derivatives)",
            NON_COMMERCIAL + "; must be used unmodified",
            "6 European languages",
            1081,
            ("*.json", "spm.model", "model.safetensors"),
        ),
        _tagger(
            "xlmr_ner_hrl",
            "XLM-R base NER-HRL (Davlan)",
            "Davlan/xlm-roberta-base-ner-hrl",
            "253f557bd8249b8515114cfd7f71974fe5fa4d2f",
            {"PER"},
            "AFL-3.0 (permissive)",
            OK_OWN,
            "10 incl. Chinese and English (no Malay or Tamil)",
            1063,
            ("*.json", "sentencepiece.bpe.model", "model.safetensors"),
        ),
    ]
}
# GLiNER multi PII v1 as ONNX, from `export-gliner` (gliner's own export_to_onnx, then slimmed).
for _variant, _label, _precision in (
    ("onnx_fp32", "fp32 ONNX", "fp32"),
    ("onnx_emb8", "ONNX, embedding table int8 (maths fp32)", "fp32+emb8"),
    ("onnx_emb8_mm8", "ONNX, embedding and MatMul weights 8-bit", "w8"),
    (
        "onnx_int8",
        "ONNX, gliner's whole-model int8 (hides nearly nothing; kept as a warning)",
        "int8",
    ),
):
    SPECS[f"gliner_multi_pii_{_variant}"] = Spec(
        f"gliner_multi_pii_{_variant}",
        f"GLiNER multi PII v1 ({_label})",
        "gliner_onnx",
        _precision,
        "Apache-2.0",
        OK_OWN,
        "6 European languages",
        GLINER_PII,
        GLINER_REV,
        (),
        {
            "labels": ["person"],
            "threshold": 0.5,
            "onnx_file": _variant.replace("onnx_", "model_").replace("model_fp32", "model")
            + ".onnx",
        },
        "onnxruntime gliner",
    )


SPECS["gliner_multi_pii_lean_emb8"] = Spec(
    "gliner_multi_pii_lean_emb8",
    "GLiNER multi PII v1 (lean runner, embedding table int8)",
    "gliner_lean",
    "fp32+emb8",
    "Apache-2.0",
    OK_OWN,
    "6 European languages",
    GLINER_PII,
    GLINER_REV,
    (),
    {"labels": ["person"], "threshold": 0.5, "onnx_file": "model_emb8.onnx"},
    "onnxruntime tokenizers numpy (no torch, no gliner package)",
)


def cache_folder(cache: Path, repo: str) -> Path:
    return cache / "hub" / ("models--" + repo.replace("/", "--"))


def fetch(spec: Spec, cache: Path) -> Path | None:
    """Download the pinned files into `cache` (HF_HOME layout); returns the snapshot folder."""
    if not spec.repo or spec.kind == "gliner_lean":
        return None
    os.environ["HF_HOME"] = str(cache)
    if (
        spec.kind == "gliner_onnx"
    ):  # the ONNX files come from `export-gliner`; only the backbone is fetched
        _backbone(cache)
        return None
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    patterns = list(spec.files) or None
    path = snapshot_download(spec.repo, revision=spec.revision, allow_patterns=patterns)
    if spec.kind == "gliner":  # gliner reads its backbone's config and tokenizer by name
        _backbone(cache)
    return Path(path)


def _backbone(cache: Path) -> None:
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    snapshot_download(
        "microsoft/mdeberta-v3-base",
        revision="a0484667b22365f84929a935b5e50a51f71f159d",
        allow_patterns=[
            "config.json",
            "tokenizer_config.json",
            "spm.model",
            "special_tokens_map.json",
        ],
    )
    refs = cache_folder(cache, "microsoft/mdeberta-v3-base") / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text("a0484667b22365f84929a935b5e50a51f71f159d")


def _snapshot(spec: Spec, cache: Path) -> str:
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    os.environ["HF_HOME"] = str(cache)
    return snapshot_download(spec.repo, revision=spec.revision, local_files_only=True)


def load(spec: Spec, cache: Path, threads: int, truth: list[dict] | None = None) -> Detect:
    """The finder for `spec`, offline, on `threads` CPU threads."""
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return _LOADERS[spec.kind](spec, cache, threads, truth)


def _oracle(spec, cache, threads, truth):
    answers = {
        c["text"]: [(c["text"].index(n), c["text"].index(n) + len(n)) for n in c["names"]]
        for c in truth or []
    }
    return lambda text: answers.get(text, [])


def _null(spec, cache, threads, truth):
    return lambda text: []


def _onnx_session(path: str, threads: int):
    import onnxruntime  # noqa: PLC0415

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
    return onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"])


def _onnx_ner(spec, cache, threads, truth):
    """A BERT token tagger exported to ONNX (bert-base-NER): windows of 500 tokens, PER only."""
    import json  # noqa: PLC0415

    import numpy  # noqa: PLC0415
    from tokenizers import Tokenizer  # noqa: PLC0415

    folder = Path(_snapshot(spec, cache))
    session = _onnx_session(str(folder / spec.options["onnx_file"]), threads)
    wanted = {item.name for item in session.get_inputs()}
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    names = {
        int(k): v for k, v in json.loads((folder / "config.json").read_text())["id2label"].items()
    }
    cls, sep = tokenizer.token_to_id("[CLS]"), tokenizer.token_to_id("[SEP]")

    def detect(text):
        encoding = tokenizer.encode(text, add_special_tokens=False)
        ids, offsets, tags = encoding.ids, encoding.offsets, ["O"] * len(encoding.ids)
        for start in range(0, max(1, len(ids)), 400):
            window = ids[start : start + 500]
            if not window:
                break
            row = numpy.array([[cls, *window, sep]], dtype=numpy.int64)
            feed = {
                "input_ids": row,
                "attention_mask": numpy.ones_like(row),
                "token_type_ids": numpy.zeros_like(row),
            }
            logits = session.run(None, {k: v for k, v in feed.items() if k in wanted})[0]
            for index, label in enumerate(logits[0][1:-1].argmax(axis=-1)):
                if tags[start + index] == "O":
                    tags[start + index] = names[int(label)]
            if start + 500 >= len(ids):
                break
        spans: list[list[int]] = []
        kind = None
        for tag, (a, b) in zip(tags, offsets, strict=True):
            prefix, _, name = tag.partition("-")
            if name != "PER":
                kind = None
                continue
            if spans and kind == name and (prefix == "I" or a == spans[-1][1]):
                spans[-1][1] = b
            else:
                spans.append([a, b])
            kind = name
        return [(a, b) for a, b in spans]

    return detect


def _hf_tagger(spec, cache, threads, truth):
    import torch  # noqa: PLC0415
    from transformers import pipeline  # noqa: PLC0415

    torch.set_num_threads(threads)
    wanted = set(spec.options["labels"])
    run = pipeline(
        "token-classification",
        model=_snapshot(spec, cache),
        aggregation_strategy="simple",
        device=-1,
    )
    return lambda text: [
        (e["start"], e["end"]) for e in run(text) if e["entity_group"].split("-")[-1] in wanted
    ]


def _gliner_predict(model, spec) -> Detect:
    o = spec.options
    return lambda text: [
        (e["start"], e["end"])
        for e in model.predict_entities(text, o["labels"], threshold=o["threshold"], flat_ner=True)
    ]


def _gliner(spec, cache, threads, truth):
    import torch  # noqa: PLC0415
    from gliner import GLiNER  # noqa: PLC0415

    torch.set_num_threads(threads)
    model = GLiNER.from_pretrained(_snapshot(spec, cache), local_files_only=True)
    model.eval()
    return _gliner_predict(model, spec)


def _gliner_onnx(spec, cache, threads, truth):
    import onnxruntime  # noqa: PLC0415
    from gliner import GLiNER  # noqa: PLC0415

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
    folder = cache / ONNX_DIR
    if not (folder / spec.options["onnx_file"]).is_file():
        raise SystemExit(
            f"{spec.name}: run `python -m tacitkit.bench export-gliner --cache {cache}` first"
        )
    model = GLiNER.from_pretrained(
        str(folder),
        local_files_only=True,
        load_onnx_model=True,
        onnx_model_file=spec.options["onnx_file"],
        session_options=options,
    )
    return _gliner_predict(model, spec)


def _gliner_lean(spec, cache, threads, truth):
    from tacitkit.models.gliner_onnx import GlinerOnnx  # noqa: PLC0415

    folder = cache / ONNX_DIR
    if not (folder / spec.options["onnx_file"]).is_file():
        raise SystemExit(
            f"{spec.name}: run `python -m tacitkit.bench export-gliner --cache {cache}` first"
        )
    model = GlinerOnnx(
        folder,
        spec.options["onnx_file"],
        tuple(spec.options["labels"]),
        spec.options["threshold"],
        threads,
    )
    return model.detect


def _presidio(spec, cache, threads, truth):
    from presidio_analyzer import AnalyzerEngine  # noqa: PLC0415
    from presidio_analyzer.nlp_engine import NlpEngineProvider  # noqa: PLC0415

    engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
        }
    ).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])
    return lambda text: [
        (r.start, r.end) for r in analyzer.analyze(text, language="en", entities=["PERSON"])
    ]


_LOADERS = {
    "oracle": _oracle,
    "null": _null,
    "onnx_ner": _onnx_ner,
    "hf_tagger": _hf_tagger,
    "gliner": _gliner,
    "gliner_onnx": _gliner_onnx,
    "gliner_lean": _gliner_lean,
    "presidio": _presidio,
}
