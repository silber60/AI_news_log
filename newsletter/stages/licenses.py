"""Code-owned 상업적 사용 rules (EVID-02, D-03, D-09).

Code decides every verdict from HF/GitHub license ids. Claude never sees or
writes these labels; it only explains them later. Unknown ids give `확인 필요`.

The GitHub token is sent only in the Authorization header. It never goes into
a URL, a log line or a returned value. Log lines carry reason codes only.
"""

import logging
import os
import re

import httpx

from newsletter.schema import (
    UNKNOWN,
    CommercialUse,
    CommercialVerdict,
    EvidenceLink,
    LicenseInfo,
)

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/repos"
GITHUB_HOST = "https://github.com/"
HF_HOST = "https://huggingface.co/"
# Same value as enrich.TIMEOUT (test-guarded). Not imported: enrich imports this
# module in 02-04, and a top-level import back would be a cycle.
TIMEOUT = 15

# Strictness order for the stricter-of rule (D-03).
RANK: dict[str, int] = {"가능": 0, "조건부": 1, "확인 필요": 2, "불가": 3}

CODE_LABEL = "코드 라이선스"
WEIGHTS_LABEL = "가중치 라이선스"


def _rows(verdict: CommercialVerdict, keys: str) -> dict[str, CommercialVerdict]:
    return dict.fromkeys(keys.split(), verdict)


# Casefolded HF license ids and GitHub SPDX ids (research §1). Copyleft is
# 조건부: commercial use is allowed with share/notice duties (A1, owner review).
LICENSE_TABLE: dict[str, CommercialVerdict] = {
    # permissive
    **_rows(
        "가능",
        "apache-2.0 mit mit-0 bsd bsd-2-clause bsd-3-clause bsd-3-clause-clear 0bsd isc zlib"
        " bsl-1.0 unlicense cc0-1.0 cc-by-2.0 cc-by-2.5 cc-by-3.0 cc-by-4.0 postgresql ncsa"
        " wtfpl afl-3.0 ecl-2.0 ms-pl artistic-2.0 upl-1.0 odc-by pddl cdla-permissive-1.0"
        " cdla-permissive-2.0",
    ),
    # copyleft
    **_rows(
        "조건부",
        "mpl-2.0 lgpl lgpl-2.1 lgpl-3.0 lgpl-lr gpl gpl-2.0 gpl-3.0 agpl-3.0 epl-1.0 epl-2.0"
        " eupl-1.1 eupl-1.2 osl-3.0 cc-by-sa-3.0 cc-by-sa-4.0 cc-by-nd-4.0 cdla-sharing-1.0"
        " odbl gfdl lppl-1.3c ofl-1.1",
    ),
    # custom / community (D-03)
    **_rows(
        "조건부",
        "openrail openrail++ bigscience-openrail-m creativeml-openrail-m"
        " bigscience-bloom-rail-1.0 bigcode-openrail-m llama2 llama3 llama3.1 llama3.2"
        " llama3.3 llama4 gemma grok2-community openmdw-1.0 openmdw-1.1 apple-ascl c-uda",
    ),
    # non-commercial / research-only
    **_rows(
        "불가",
        "cc-by-nc-2.0 cc-by-nc-3.0 cc-by-nc-4.0 cc-by-nc-nd-3.0 cc-by-nc-nd-4.0"
        " cc-by-nc-sa-2.0 cc-by-nc-sa-3.0 cc-by-nc-sa-4.0 fair-noncommercial-research-license"
        " deepfloyd-if-license intel-research h-research apple-amlr",
    ),
}

# cardData.license_name values when the license id is "other" (A2).
OTHER_NAMES: dict[str, CommercialVerdict] = _rows(
    "조건부", "qwen tongyi-qianwen deepseek deepseek-license"
)
NC_KEYWORDS = ("non-commercial", "noncommercial", "-nc-", "research")

# Same pattern as enrich.REPO_ID_RE (test-guarded; see TIMEOUT for why it is copied).
REPO_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,96}$")
# A11: fine-tunes of these families inherit a custom base license.
BASE_FAMILY_RE = re.compile(r"^base_model:(?:[\w-]+:)?(?:meta-llama/|google/gemma)", re.IGNORECASE)


def _normalize(value: str) -> str:
    key = value.strip().casefold()
    for suffix in ("-only", "-or-later"):
        if key.endswith(suffix):
            key = key.removesuffix(suffix)
    return key


def _lookup_name(name: object) -> CommercialVerdict:
    if not isinstance(name, str) or not name.strip():
        return UNKNOWN
    key = name.strip().casefold()
    if any(k in key for k in NC_KEYWORDS):
        return "불가"
    return OTHER_NAMES.get(key, UNKNOWN)


def _lookup_one(value: object, name: object) -> CommercialVerdict:
    if not isinstance(value, str) or not value.strip():
        return UNKNOWN
    key = _normalize(value)
    if key == "other":
        return _lookup_name(name)
    return LICENSE_TABLE.get(key, UNKNOWN)


def lookup(license: str | list | None, name: str | None = None) -> CommercialVerdict:
    """Verdict for one HF license id or GitHub SPDX id; a list takes the strictest."""
    if isinstance(license, list):
        verdicts = [_lookup_one(v, name) for v in license]
        if not verdicts:
            return UNKNOWN
        return max(verdicts, key=RANK.__getitem__)
    return _lookup_one(license, name)


# --------------------------------------------------------------- weights side


def resolve_license_link(link: str | None, model_id: str) -> str:
    """An https URL on huggingface.co or github.com; else the model page (T-02-06)."""
    if not isinstance(model_id, str) or not REPO_ID_RE.fullmatch(model_id) or ".." in model_id:
        return f"{HF_HOST}models"
    page = f"{HF_HOST}{model_id}"
    if not isinstance(link, str) or not link or any(c in link for c in "?#\\") or ".." in link:
        return page
    if any(c.isspace() for c in link):
        return page
    if link.startswith((HF_HOST, GITHUB_HOST)):
        return link
    rel = link.removeprefix("./")
    if not rel or ":" in rel or rel.startswith("/"):
        return page
    return f"{page}/blob/main/{rel}"


def _license_tag(tags: object) -> str | None:
    for t in tags if isinstance(tags, list) else []:
        if isinstance(t, str) and t.startswith("license:") and t.removeprefix("license:").strip():
            return t.removeprefix("license:").strip()
    return None


def weights_license(model: dict | None, model_id: str) -> tuple[LicenseInfo, CommercialVerdict]:
    """Weights-side license from HF metadata only (D-09). README text is never read.

    Read order: cardData.license, then license_name when it is "other", then the
    first license: tag. Gated and base-model guards move 가능 to 조건부 (D-03, A11).
    """
    page = resolve_license_link(None, model_id)
    if not isinstance(model, dict):
        return LicenseInfo(source_url=page), UNKNOWN
    card = model.get("cardData") if isinstance(model.get("cardData"), dict) else {}
    lic = card.get("license")
    if isinstance(lic, list):
        lic = [v for v in lic if isinstance(v, str) and v.strip()] or None
    elif not isinstance(lic, str) or not lic.strip():
        lic = None
    if lic is None:
        lic = _license_tag(model.get("tags"))
    name = card.get("license_name") if isinstance(card.get("license_name"), str) else None
    verdict = lookup(lic, name)

    tags = model.get("tags") if isinstance(model.get("tags"), list) else []
    if verdict == "가능" and model.get("gated") not in (False, None):
        verdict = "조건부"
    if verdict == "가능" and any(isinstance(t, str) and BASE_FAMILY_RE.match(t) for t in tags):
        verdict = "조건부"

    spdx = ", ".join(lic) if isinstance(lic, list) else lic
    info = LicenseInfo(
        spdx_id=spdx,
        name=name,
        source_url=resolve_license_link(card.get("license_link"), model_id),
    )
    return info, verdict


# ------------------------------------------------------------------ code side


def github_license(client: httpx.Client, owner: str, repo: str) -> dict:
    """One GET to the GitHub license API. Never raises, never logs the token.

    owner/repo must come from enrich.parse_repo (allowlist regex).
    """
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out: dict = {"status": "error", "spdx_id": None, "name": None, "html_url": None}
    try:
        resp = client.get(
            f"{GITHUB_API}/{owner}/{repo}/license",
            headers=headers,
            timeout=TIMEOUT,
            follow_redirects=False,
        )
        if resp.status_code == 404:
            out["status"] = "none"
        elif resp.status_code != 200:
            out["status"] = f"http_{resp.status_code}"
        else:
            data = resp.json()
            lic = data.get("license") if isinstance(data, dict) else None
            lic = lic if isinstance(lic, dict) else {}
            html_url = data.get("html_url") if isinstance(data, dict) else None
            out.update(
                status="ok",
                spdx_id=lic.get("spdx_id") if isinstance(lic.get("spdx_id"), str) else None,
                name=lic.get("name") if isinstance(lic.get("name"), str) else None,
                html_url=html_url
                if isinstance(html_url, str) and html_url.startswith(GITHUB_HOST)
                else None,
            )
    except (httpx.HTTPError, ValueError) as e:
        out["status"] = f"error_{type(e).__name__}"
    if out["status"] != "ok":
        log.info("github_license=none reason=%s", out["status"])
    return out


def code_license(record: dict) -> tuple[LicenseInfo, CommercialVerdict]:
    """LicenseInfo and verdict for a github_license() record."""
    if not isinstance(record, dict) or record.get("status") != "ok":
        return LicenseInfo(), UNKNOWN
    spdx = record.get("spdx_id")
    if not isinstance(spdx, str) or spdx.casefold() == "noassertion":
        spdx = None
    info = LicenseInfo(spdx_id=spdx, name=record.get("name"), source_url=record.get("html_url"))
    return info, lookup(spdx)


# ------------------------------------------------------------------- combined


def commercial_use(
    code: tuple[LicenseInfo, CommercialVerdict] | None,
    weights: tuple[LicenseInfo, CommercialVerdict] | None,
) -> CommercialUse:
    """Stricter of the existing sides (D-03). None means that side does not exist.

    Evidence lists the decisive side first (on a tie, the weights side).
    """
    sides = [
        (label, side)
        for label, side in ((WEIGHTS_LABEL, weights), (CODE_LABEL, code))
        if side is not None
    ]
    if not sides:
        return CommercialUse(verdict=UNKNOWN)
    verdict = max((s[1] for _, s in sides), key=RANK.__getitem__)
    decisive = next(i for i, (_, s) in enumerate(sides) if s[1] == verdict)
    ordered = [sides[decisive]] + [s for i, s in enumerate(sides) if i != decisive]
    evidence = [
        EvidenceLink(label=label, url=info.source_url)
        for label, (info, _) in ordered
        if info.source_url
    ]
    return CommercialUse(
        verdict=verdict,
        code_license=code[0] if code is not None else None,
        weights_license=weights[0] if weights is not None else None,
        evidence=evidence,
    )
