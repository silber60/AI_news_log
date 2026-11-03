"""Code-owned 상업적 사용 rules (EVID-02, D-03, D-09).

Code decides every verdict from HF/GitHub license ids. Claude never sees or
writes these labels; it only explains them later. Unknown ids give `확인 필요`.

The GitHub token is sent only in the Authorization header. It never goes into
a URL, a log line or a returned value. Log lines carry reason codes only.
"""

import logging
import os

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

LICENSE_TABLE: dict[str, CommercialVerdict] = {
    "apache-2.0": "가능",
    "mit": "가능",
}


def _normalize(value: str) -> str:
    key = value.strip().casefold()
    for suffix in ("-only", "-or-later"):
        if key.endswith(suffix):
            key = key.removesuffix(suffix)
    return key


def _lookup_one(value: object, name: object) -> CommercialVerdict:
    if not isinstance(value, str) or not value.strip():
        return UNKNOWN
    return LICENSE_TABLE.get(_normalize(value), UNKNOWN)


def lookup(license: str | list | None, name: str | None = None) -> CommercialVerdict:
    """Verdict for one HF license id or GitHub SPDX id; a list takes the strictest."""
    if isinstance(license, list):
        verdicts = [_lookup_one(v, name) for v in license]
        if not verdicts:
            return UNKNOWN
        return max(verdicts, key=RANK.__getitem__)
    return _lookup_one(license, name)


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
