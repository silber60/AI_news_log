"""Code-decided practical verdicts (EVID-03..05, D-05, D-11, D-15).

Pure functions: no I/O and no logging. Every verdict here comes from the HF/GitHub
facts that enrich captured. Claude never decides a verdict; it only explains it later.

`enforce_evidence` runs last: a positive verdict without evidence on huggingface.co
or github.com falls back to `확인 필요`.
"""

from typing import Any

from newsletter.schema import UNKNOWN, EvidenceLink, Hardware, Item, LocalRun, PocReadiness

HF_HOST = "https://huggingface.co/"
GITHUB_HOST = "https://github.com/"
EVIDENCE_HOSTS = (HF_HOST, GITHUB_HOST)

# PoC evidence label for gated weights; render picks the "승인 받고" phrase from it.
POC_GATED_LABEL = "HF 모델 (승인 필요)"

POC_POSITIVE = ("바로 가능", "코드만")
COMMERCIAL_POSITIVE = ("가능", "조건부")
LOCAL_RUN_POSITIVE = ("가능", "제한적")

# D-04, D-10: fp16/bf16 weights (2 bytes/param) plus 20% for activations and context.
BYTES_PER_PARAM = 2
VRAM_OVERHEAD = 1.2
CONSUMER_GPU_GB = 24.0  # RTX 4090 class, inclusive
SERVER_GPU_GB = 80.0  # one server GPU, inclusive
FLOAT_DTYPES = frozenset({"F64", "F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"})
# Packed quantization stores weights in int dtypes, so `total` is not the runtime size.
NON_FLOAT_MAX_SHARE = 0.01
DERIVED_TAG_PREFIXES = ("base_model:adapter:", "base_model:quantized:")


def poc(item: Item, f: dict[str, Any]) -> PocReadiness:
    """PoC verdict from the enrich facts, first match wins (research §2).

    Call only after the HF paper fetch succeeded: `논문만` is a negative claim (D-15).
    The has_* flags stay as enrich set them (True or None, never False).
    """
    base = item.poc
    spaces = f.get("spaces") or []
    model_id = f.get("model_id")
    if f.get("has_demo") and spaces:
        verdict, ev = (
            "바로 가능",
            [EvidenceLink(label="HF 데모", url=f"{HF_HOST}spaces/{spaces[0]}")],
        )
    elif f.get("has_weights") and model_id:
        label = POC_GATED_LABEL if f.get("gated") else "HF 모델"
        verdict, ev = "바로 가능", [EvidenceLink(label=label, url=f"{HF_HOST}{model_id}")]
    elif f.get("has_weights"):
        # Linked weights whose id failed the allowlist: no page to cite.
        verdict, ev = "바로 가능", []
    elif f.get("has_code"):
        ev = [EvidenceLink(label="GitHub", url=item.github_url)] if item.github_url else []
        verdict = "코드만"
    else:
        verdict, ev = "논문만", [EvidenceLink(label="논문", url=item.hf_url)]
    return base.model_copy(update={"verdict": verdict, "evidence": ev})


def _valid_total(n: Any) -> int | None:
    """Same rule as enrich.param_total: a positive int, never a bool."""
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None


def _vram_reliable(model: dict, total: int) -> bool:
    tags = model.get("tags") or []
    if any(isinstance(t, str) and t.startswith(DERIVED_TAG_PREFIXES) for t in tags):
        return False
    st = model.get("safetensors")
    params = st.get("parameters") if isinstance(st, dict) else None
    if not isinstance(params, dict):
        return True
    other = 0
    for dtype, n in params.items():
        if dtype in FLOAT_DTYPES:
            continue
        if _valid_total(n) is None and n != 0:
            return False
        other += n
    return other <= NON_FLOAT_MAX_SHARE * total


def _local_run(gb: float) -> LocalRun:
    if gb <= CONSUMER_GPU_GB:
        return "가능"
    if gb <= SERVER_GPU_GB:
        return "제한적"
    return "불가"


def hardware(model: dict | None, model_id: str | None, param_count: int | None) -> Hardware:
    """EVID-04: estimated VRAM from the safetensors total only (D-10).

    Model-name tokens and config.json are never read. A guard hit keeps the
    parameter count but leaves the estimate and the label unknown.
    """
    total = _valid_total(param_count)
    if total is None:
        return Hardware()
    if not isinstance(model, dict) or not _vram_reliable(model, total):
        return Hardware(param_count=total)
    gb = round(total * BYTES_PER_PARAM * VRAM_OVERHEAD / 1e9, 1)
    ev = [EvidenceLink(label="HF 모델", url=f"{HF_HOST}{model_id}")] if model_id else []
    return Hardware(param_count=total, est_vram_gb=gb, local_run=_local_run(gb), evidence=ev)


def _on_hosts(evidence: list[EvidenceLink]) -> bool:
    return bool(evidence) and all(e.url.startswith(EVIDENCE_HOSTS) for e in evidence)


def enforce_evidence(item: Item) -> Item:
    """EVID-05, D-11: no positive verdict survives without its evidence.

    Evidence must be non-empty and every URL on huggingface.co or github.com.
    직접 사용 needs a repo, project page or Space. Negatives pass unchanged.
    """
    update: dict[str, Any] = {}
    c = item.commercial
    if c.verdict in COMMERCIAL_POSITIVE and not _on_hosts(c.evidence):
        update["commercial"] = c.model_copy(update={"verdict": UNKNOWN, "reason_ko": None})
    p = item.poc
    if p.verdict in POC_POSITIVE and not _on_hosts(p.evidence):
        update["poc"] = p.model_copy(update={"verdict": UNKNOWN, "reason_ko": None})
    h = item.hardware
    if h.local_run in LOCAL_RUN_POSITIVE and not _on_hosts(h.evidence):
        update["hardware"] = h.model_copy(update={"local_run": UNKNOWN, "est_vram_gb": None})
    g = item.claude_gpt
    if g.verdict == "직접 사용" and not (item.github_url or item.project_url or p.has_demo):
        update["claude_gpt"] = g.model_copy(update={"verdict": UNKNOWN, "reason_ko": None})
    return item.model_copy(update=update) if update else item


def finalize(items: list[Item]) -> list[Item]:
    """Last verdict step before the Issue is built."""
    return [enforce_evidence(it) for it in items]
