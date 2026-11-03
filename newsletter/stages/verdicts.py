"""Code-decided practical verdicts (EVID-03..05, D-05, D-11, D-15).

Pure functions: no I/O and no logging. Every verdict here comes from the HF/GitHub
facts that enrich captured. Claude never decides a verdict; it only explains it later.

`enforce_evidence` runs last: a positive verdict without evidence on huggingface.co
or github.com falls back to `확인 필요`.
"""

from typing import Any

from newsletter.schema import UNKNOWN, EvidenceLink, Item, PocReadiness

HF_HOST = "https://huggingface.co/"
GITHUB_HOST = "https://github.com/"
EVIDENCE_HOSTS = (HF_HOST, GITHUB_HOST)

# PoC evidence label for gated weights; render picks the "승인 받고" phrase from it.
POC_GATED_LABEL = "HF 모델 (승인 필요)"

POC_POSITIVE = ("바로 가능", "코드만")


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


def _on_hosts(evidence: list[EvidenceLink]) -> bool:
    return bool(evidence) and all(e.url.startswith(EVIDENCE_HOSTS) for e in evidence)


def enforce_evidence(item: Item) -> Item:
    """EVID-05: no positive verdict survives without evidence on HF or GitHub."""
    update: dict[str, Any] = {}
    if item.poc.verdict in POC_POSITIVE and not _on_hosts(item.poc.evidence):
        update["poc"] = item.poc.model_copy(update={"verdict": UNKNOWN, "reason_ko": None})
    return item.model_copy(update=update) if update else item


def finalize(items: list[Item]) -> list[Item]:
    """Last verdict step before the Issue is built."""
    return [enforce_evidence(it) for it in items]
