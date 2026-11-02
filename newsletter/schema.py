"""Data contracts.

`Issue` (schema_version 1) is FROZEN in Phase 1. Later phases fill its fields;
they do not add or rename them outside a planned phase. The committed snapshot
`schema/issue.schema.v1.json` guards against drift.

Code owns ranks, URLs, affiliation and every verdict. Claude only fills
`ItemAnalysisLLM` (and, in later phases, other small sub-models) which code
merges into `Item` / `Issue`.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

SCHEMA_VERSION = 1

# Enum labels quoted from .planning/REQUIREMENTS.md.
AiType = Literal["LLM", "비전", "멀티모달", "음성", "에이전트", "이미지/비디오 생성", "기타"]
CommercialVerdict = Literal["가능", "조건부", "불가", "확인 필요"]
PocVerdict = Literal["바로 가능", "코드만", "논문만", "확인 필요"]
ClaudeGptVerdict = Literal["직접 사용", "기법 적용 가능", "해당 없음", "확인 필요"]
SkillGptFit = Literal["Claude Skill", "GPTs", "둘 다", "해당 없음"]
# EVID-04 does not enumerate labels; confirmed by the owner at the Phase 1 freeze.
LocalRun = Literal["가능", "제한적", "불가", "확인 필요"]


def _require_https(v: str) -> str:
    if not v.startswith("https://"):
        raise ValueError("URL must start with https://")
    return v


HttpsUrl = Annotated[str, AfterValidator(_require_https)]


class Strict(BaseModel):
    # Not frozen: stages update copies with model_copy(update=...).
    model_config = ConfigDict(extra="forbid")


class EvidenceLink(Strict):
    label: str
    url: HttpsUrl


class LicenseInfo(Strict):
    spdx_id: str | None = None
    name: str | None = None
    source_url: HttpsUrl | None = None


class CommercialUse(Strict):  # Phase 2 (EVID-02, ANLY-04)
    verdict: CommercialVerdict = "확인 필요"
    code_license: LicenseInfo | None = None
    weights_license: LicenseInfo | None = None
    evidence: list[EvidenceLink] = []
    reason_ko: str | None = None


class PocReadiness(Strict):  # Phase 2 (EVID-03)
    verdict: PocVerdict = "확인 필요"
    has_weights: bool | None = None
    has_code: bool | None = None
    has_demo: bool | None = None
    evidence: list[EvidenceLink] = []
    reason_ko: str | None = None


class Hardware(Strict):  # Phase 2 (EVID-04)
    param_count: int | None = None
    est_vram_gb: float | None = None
    local_run: LocalRun = "확인 필요"
    evidence: list[EvidenceLink] = []


class ClaudeGptUse(Strict):  # Phase 2 (ANLY-02)
    verdict: ClaudeGptVerdict = "확인 필요"
    reason_ko: str | None = None


class SkillGptFitInfo(Strict):  # Phase 3 (HILT-01)
    fit: SkillGptFit = "해당 없음"
    reason_ko: str | None = None


class Item(Strict):
    # Code-owned facts (Phase 1)
    rank: int
    paper_id: str
    title_en: str
    upvotes: int
    num_comments: int
    submitted_on_daily_at: date
    affiliation: str | None = None  # D-08: organization.fullname
    hf_url: HttpsUrl  # D-06: always
    arxiv_url: HttpsUrl  # D-06: always
    github_url: HttpsUrl | None = None  # D-06: only when present
    project_url: HttpsUrl | None = None  # D-06: only when present
    # Claude-written (Phase 1)
    title_ko: str
    ai_type: AiType
    summary_ko: str
    use_ideas_ko: list[str] = []
    # Later phases (defaults keep Phase 1 valid)
    commercial: CommercialUse = CommercialUse()
    poc: PocReadiness = PocReadiness()
    hardware: Hardware = Hardware()
    claude_gpt: ClaudeGptUse = ClaudeGptUse()
    skill_gpt: SkillGptFitInfo = SkillGptFitInfo()

    @model_validator(mode="after")
    def _check_ideas(self) -> Item:
        if len(self.use_ideas_ko) > 2:
            raise ValueError("use_ideas_ko allows at most 2 entries")
        return self


class Highlight(Strict):  # Phase 3 (HILT-02/03)
    rank: int
    tag: Literal["Claude Skill", "GPTs", "둘 다"]
    why_ko: str
    how_ko: str


class Explainer(Strict):  # Phase 3 (EXPL-01/02, D-16)
    topic: str
    body_ko: str
    related_ranks: list[int]


class Issue(Strict):
    schema_version: Literal[1] = 1
    issue_id: str
    week_start: date
    week_end: date
    generated_at: datetime
    model: str
    fetch_method: Literal["week", "date"]
    items: list[Item]
    trend_ko: str | None = None  # Phase 2 (ANLY-05)
    highlights: list[Highlight] = []  # Phase 3 (HILT-02/03)
    explainer: Explainer | None = None  # Phase 3 (D-16)

    @model_validator(mode="after")
    def _check_contract(self) -> Issue:
        n = len(self.items)
        if not 1 <= n <= 10:
            raise ValueError("items must hold 1..10 entries")
        if [it.rank for it in self.items] != list(range(1, n + 1)):
            raise ValueError("item ranks must be contiguous 1..N in order")
        ids = [it.paper_id for it in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("paper_id must be unique")
        ranks = set(range(1, n + 1))
        if len(self.highlights) > 3:
            raise ValueError("at most 3 highlights")
        if any(h.rank not in ranks for h in self.highlights):
            raise ValueError("highlight rank must reference an item")
        if self.explainer is not None and any(
            r not in ranks for r in self.explainer.related_ranks
        ):
            raise ValueError("explainer related_ranks must reference items")
        return self


# ---- HF input models (untrusted; unknown keys ignored) ----


class HfInput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HfPaper(HfInput):
    id: str
    title: str
    summary: str = ""
    upvotes: int = 0
    publishedAt: datetime | None = None
    submittedOnDailyAt: datetime
    ai_summary: str | None = None
    ai_keywords: list[str] | None = None
    githubRepo: str | None = None
    githubStars: int | None = None
    projectPage: str | None = None


class HfOrg(HfInput):
    name: str | None = None
    fullname: str | None = None


class HfEntry(HfInput):
    paper: HfPaper
    title: str | None = None
    numComments: int = 0
    organization: HfOrg | None = None


# ---- Claude output model (no rank, URL or verdict fields) ----


class ItemAnalysisLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title_ko: str  # D-04: Korean gloss, model names and AI terms in English
    ai_type: AiType  # ANLY-01 closed enum
    summary_ko: str  # ANLY-03: one sentence, <= 80 chars (checked in code)
    use_ideas_ko: list[str]  # D-07: 0..2 grounded ideas
