"""Code verdicts (EVID-03..05): PoC table, VRAM rules, evidence enforcement."""

import pytest

from newsletter.schema import UNKNOWN, EvidenceLink, Item
from newsletter.stages import verdicts
from newsletter.stages.verdicts import POC_GATED_LABEL


@pytest.fixture
def item(issue_w44) -> Item:
    """W44 rank 1 with a repo, every verdict at its default."""
    return issue_w44.items[0].model_copy(update={"github_url": "https://github.com/acme/repo"})


def _f(**kw) -> dict:
    base = {
        "has_weights": False,
        "has_code": False,
        "has_demo": False,
        "spaces": [],
        "gated": False,
        "model_id": None,
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------------ PoC


def test_poc_demo_gives_ready_with_space_evidence(item):
    out = verdicts.poc(item, _f(has_demo=True, spaces=["org/demo"]))
    assert out.verdict == "바로 가능"
    assert [(e.label, e.url) for e in out.evidence] == [
        ("HF 데모", "https://huggingface.co/spaces/org/demo")
    ]


def test_poc_demo_outranks_weights(item):
    f = _f(has_demo=True, spaces=["org/demo"], has_weights=True, model_id="org/m", has_code=True)
    out = verdicts.poc(item, f)
    assert out.evidence[0].label == "HF 데모"


def test_poc_open_weights_cite_model_page(item):
    out = verdicts.poc(item, _f(has_weights=True, model_id="org/m", has_code=True))
    assert out.verdict == "바로 가능"
    assert [(e.label, e.url) for e in out.evidence] == [("HF 모델", "https://huggingface.co/org/m")]


def test_poc_gated_weights_use_gated_label(item):
    out = verdicts.poc(item, _f(has_weights=True, gated=True, model_id="org/m"))
    assert out.verdict == "바로 가능"
    assert out.evidence[0].label == POC_GATED_LABEL
    assert out.evidence[0].url == "https://huggingface.co/org/m"


def test_poc_code_only_cites_repo(item):
    out = verdicts.poc(item, _f(has_code=True))
    assert out.verdict == "코드만"
    assert [(e.label, e.url) for e in out.evidence] == [("GitHub", "https://github.com/acme/repo")]


def test_poc_code_only_without_github_url_has_no_evidence(item):
    out = verdicts.poc(item.model_copy(update={"github_url": None}), _f(has_code=True))
    assert out.verdict == "코드만"
    assert out.evidence == []


def test_poc_paper_only_cites_hf_paper(item):
    out = verdicts.poc(item, _f())
    assert out.verdict == "논문만"
    assert [(e.label, e.url) for e in out.evidence] == [("논문", item.hf_url)]


def test_poc_keeps_has_flags_never_false(item):
    flagged = item.model_copy(update={"poc": item.poc.model_copy(update={"has_code": True})})
    out = verdicts.poc(flagged, _f(has_code=True))
    assert (out.has_weights, out.has_code, out.has_demo) == (None, True, None)
    out = verdicts.poc(item, _f())
    assert (out.has_weights, out.has_code, out.has_demo) == (None, None, None)


# -------------------------------------------------------- evidence enforcement


def _with_poc(item: Item, verdict: str, evidence: list[EvidenceLink]) -> Item:
    return item.model_copy(
        update={"poc": item.poc.model_copy(update={"verdict": verdict, "evidence": evidence})}
    )


@pytest.mark.parametrize("verdict", ["바로 가능", "코드만"])
def test_enforce_evidence_drops_poc_without_evidence(item, verdict):
    out = verdicts.enforce_evidence(_with_poc(item, verdict, []))
    assert out.poc.verdict == UNKNOWN


def test_enforce_evidence_drops_poc_off_allowed_hosts(item):
    ev = [EvidenceLink(label="GitHub", url="https://gitlab.com/acme/repo")]
    assert verdicts.enforce_evidence(_with_poc(item, "코드만", ev)).poc.verdict == UNKNOWN


def test_enforce_evidence_keeps_backed_poc_and_negatives(item):
    ev = [EvidenceLink(label="GitHub", url="https://github.com/acme/repo")]
    assert verdicts.enforce_evidence(_with_poc(item, "코드만", ev)).poc.verdict == "코드만"
    assert verdicts.enforce_evidence(_with_poc(item, "논문만", [])).poc.verdict == "논문만"


def test_finalize_maps_every_item(issue_w44):
    items = [_with_poc(it, "바로 가능", []) for it in issue_w44.items]
    assert all(it.poc.verdict == UNKNOWN for it in verdicts.finalize(items))


# ----------------------------------------------------------------------- VRAM

DETECTOR = "liamdugan/detector-scope"


def _model(total, parameters=None, tags=None) -> dict:
    st = {"total": total}
    if parameters is not None:
        st["parameters"] = parameters
    return {"id": "org/m", "safetensors": st, "tags": tags or []}


def test_hardware_vram_detector_scope_is_personal_gpu():
    model = {
        "safetensors": {"parameters": {"F32": 302130176}, "total": 302130176},
        "tags": ["base_model:google/gemma-2-2b", "base_model:finetune:google/gemma-2-2b"],
    }
    hw = verdicts.hardware(model, DETECTOR, 302130176)
    assert (hw.param_count, hw.est_vram_gb, hw.local_run) == (302130176, 0.7, "가능")
    assert [(e.label, e.url) for e in hw.evidence] == [
        ("HF 모델", "https://huggingface.co/liamdugan/detector-scope")
    ]


@pytest.mark.parametrize(
    ("total", "gb", "label"),
    [
        (10_000_000_000, 24.0, "가능"),
        (10_041_666_667, 24.1, "제한적"),
        (33_333_333_333, 80.0, "제한적"),
        (33_375_000_000, 80.1, "불가"),
    ],
)
def test_hardware_vram_boundaries_are_inclusive(total, gb, label):
    hw = verdicts.hardware(_model(total, {"BF16": total}), "org/m", total)
    assert (hw.est_vram_gb, hw.local_run) == (gb, label)
    assert hw.evidence[0].url == "https://huggingface.co/org/m"


@pytest.mark.parametrize("total", [None, 0, -5, True, "7000", 7.5])
def test_hardware_vram_unknown_without_valid_total(total):
    model = None if total is None else _model(total)
    hw = verdicts.hardware(model, "org/m", total)
    assert (hw.param_count, hw.est_vram_gb, hw.local_run) == (None, None, UNKNOWN)
    assert hw.evidence == []


def test_hardware_vram_unknown_without_safetensors():
    hw = verdicts.hardware({"id": "org/m", "tags": []}, "org/m", None)
    assert (hw.est_vram_gb, hw.local_run, hw.evidence) == (None, UNKNOWN, [])


def test_hardware_vram_packed_int_dtype_is_unknown_but_keeps_count():
    total = 6_739_777_536
    model = _model(total, {"I32": 6_476_005_376, "F16": 263_772_160})
    hw = verdicts.hardware(model, "org/m", total)
    assert (hw.param_count, hw.est_vram_gb, hw.local_run) == (total, None, UNKNOWN)
    assert hw.evidence == []


def test_hardware_vram_small_int_share_is_tolerated():
    total = 1_000_000_000
    model = _model(total, {"BF16": total - 5_000_000, "I64": 5_000_000})
    assert verdicts.hardware(model, "org/m", total).local_run == "가능"


@pytest.mark.parametrize(
    "tag", ["base_model:adapter:meta-llama/Llama-3.1-8B", "base_model:quantized:org/base"]
)
def test_hardware_vram_adapter_or_quantized_base_is_unknown(tag):
    total = 7_000_000_000
    hw = verdicts.hardware(_model(total, {"BF16": total}, [tag]), "org/m", total)
    assert (hw.param_count, hw.est_vram_gb, hw.local_run) == (total, None, UNKNOWN)


def test_hardware_vram_float_mix_counts_as_float():
    total = 684_489_845_504  # DeepSeek-V3
    params = {"BF16": 3_918_786_560, "F8_E4M3": 680_571_043_840, "F32": 15_000}
    hw = verdicts.hardware(_model(total, params), "deepseek-ai/DeepSeek-V3", total)
    assert hw.local_run == "불가"
    assert hw.est_vram_gb == round(total * 2.4 / 1e9, 1)
    assert hw.evidence  # a decided 불가 still cites its page


# ---------------------------------------------------- evidence (all four fields)

HF_EV = [EvidenceLink(label="HF 모델", url="https://huggingface.co/org/m")]
OFF_HOST = [EvidenceLink(label="라이선스", url="https://example.com/LICENSE")]


def _bare(item: Item) -> Item:
    """No repo, project page or Space: nothing backs 직접 사용."""
    return item.model_copy(update={"github_url": None, "project_url": None})


def _set(item: Item, **fields) -> Item:
    return item.model_copy(
        update={k: getattr(item, k).model_copy(update=v) for k, v in fields.items()}
    )


@pytest.mark.parametrize("verdict", ["가능", "조건부"])
@pytest.mark.parametrize("evidence", [[], OFF_HOST])
def test_enforce_evidence_commercial_positive_needs_hf_or_github(item, verdict, evidence):
    it = _set(item, commercial={"verdict": verdict, "evidence": evidence, "reason_ko": "이유"})
    out = verdicts.enforce_evidence(it).commercial
    assert (out.verdict, out.reason_ko) == (UNKNOWN, None)


def test_enforce_evidence_commercial_backed_survives(item):
    it = _set(item, commercial={"verdict": "조건부", "evidence": HF_EV, "reason_ko": "이유"})
    assert verdicts.enforce_evidence(it).commercial.verdict == "조건부"
    mixed = _set(item, commercial={"verdict": "가능", "evidence": HF_EV + OFF_HOST})
    assert verdicts.enforce_evidence(mixed).commercial.verdict == UNKNOWN


@pytest.mark.parametrize("label", ["가능", "제한적"])
def test_enforce_evidence_hardware_keeps_param_count(item, label):
    it = _set(item, hardware={"local_run": label, "est_vram_gb": 6.3, "param_count": 2_610_000_000})
    out = verdicts.enforce_evidence(it).hardware
    assert (out.local_run, out.est_vram_gb, out.param_count) == (UNKNOWN, None, 2_610_000_000)
    backed = _set(item, hardware={"local_run": label, "est_vram_gb": 6.3, "evidence": HF_EV})
    assert verdicts.enforce_evidence(backed).hardware.local_run == label


def test_enforce_evidence_direct_claude_gpt_needs_an_artifact(item):
    direct = {"verdict": "직접 사용", "reason_ko": "이유"}
    out = verdicts.enforce_evidence(_set(_bare(item), claude_gpt=direct)).claude_gpt
    assert (out.verdict, out.reason_ko) == (UNKNOWN, None)
    assert verdicts.enforce_evidence(_set(item, claude_gpt=direct)).claude_gpt.verdict == (
        "직접 사용"
    )
    proj = _bare(item).model_copy(update={"project_url": "https://acme.example/p"})
    assert verdicts.enforce_evidence(_set(proj, claude_gpt=direct)).claude_gpt.verdict == (
        "직접 사용"
    )
    demo = _set(_bare(item), claude_gpt=direct, poc={"has_demo": True})
    assert verdicts.enforce_evidence(demo).claude_gpt.verdict == "직접 사용"


def test_enforce_evidence_negatives_pass_unchanged(item):
    it = _set(
        _bare(item),
        commercial={"verdict": "불가", "reason_ko": "이유"},
        poc={"verdict": "논문만"},
        hardware={"local_run": "불가", "est_vram_gb": 174.5},
        claude_gpt={"verdict": "해당 없음", "reason_ko": "이유"},
    )
    assert verdicts.enforce_evidence(it) == it
    technique = _set(_bare(item), claude_gpt={"verdict": "기법 적용 가능"})
    assert verdicts.enforce_evidence(technique).claude_gpt.verdict == "기법 적용 가능"


POSITIVES = {
    "commercial": ("verdict", ("가능", "조건부", UNKNOWN)),
    "poc": ("verdict", ("바로 가능", "코드만", UNKNOWN)),
    "hardware": ("local_run", ("가능", "제한적", UNKNOWN)),
    "claude_gpt": ("verdict", ("직접 사용", UNKNOWN)),
}


def test_enforce_evidence_property_no_positive_survives_without_evidence(item):
    import itertools

    fields = list(POSITIVES)
    combos = itertools.product(*(POSITIVES[f][1] for f in fields))
    n = 0
    for combo in combos:
        upd = {f: {POSITIVES[f][0]: v} for f, v in zip(fields, combo, strict=True)}
        upd["hardware"]["est_vram_gb"] = 10.0
        out = verdicts.enforce_evidence(_set(_bare(item), **upd))
        for f in fields:
            assert getattr(getattr(out, f), POSITIVES[f][0]) == UNKNOWN, (f, combo)
        n += 1
    assert n == 3 * 3 * 3 * 2
