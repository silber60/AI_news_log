"""Code-decided model facts from the HF paper/model APIs (ANLY-08, D-07).

Claude never writes 크기 / 학습 데이터 / 공개 범위. This stage reads them from HF
and leaves `UNKNOWN` ("확인 필요") when HF does not say. Absence is never written
as a negative fact: `poc.has_*` is only ever set to True and
`hardware.param_count` only to a positive int. Verdicts are not touched (Phase 2).

Enrichment is non-fatal. Any HTTP or parse problem keeps the defaults for that
item and logs a reason code. Logs carry ranks and codes only, never ids,
dataset names, URLs or response bodies.

The per-item image (D-08, D-09, D-18) is the first candidate that passes every
filter: HF-upload images in `paper.mediaUrls` first, then images from the repo
README on raw.githubusercontent.com, fetched only when no HF image passed. Code
reads only the first 64 KB of each candidate to get the size from the header,
and keeps it only when it is wide enough for the 576 px card, banner-like, at
most 1 MB in total and served without a redirect. The README is read up to
256 KB, used only for image URLs, and never sent to Claude or logged.
"""

import html
import logging
import re
import warnings
from io import BytesIO
from typing import Any

import httpx
from PIL import Image
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from newsletter.schema import (
    IMAGE_HOST,
    IMAGE_HOSTS,
    IMAGE_URL_MAX,
    RAW_IMAGE_HOST,
    UNKNOWN,
    EvidenceLink,
    HfEntry,
    Item,
    ItemImage,
)

log = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co"
TIMEOUT = 15
ATTEMPTS = 2
# Exponential backoff base in seconds, read per call so tests can set it to 0.
RETRY_WAIT_MULTIPLIER: float = 1.0
RETRY_WAIT_MAX = 10

MODEL_EXPAND = "expand[]=safetensors&expand[]=cardData&expand[]=gated&expand[]=tags"
# T-01.1-08: ids from HF JSON go into URL paths only after this allowlist.
REPO_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,96}$")
PAPER_ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")

DATASET_SHOWN = 3
DATASET_ID_MAX = 40

# D-11 / DSGN-07: one per-item image, from the paper's HF upload media only.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif")
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif"}
IMAGE_MAX_BYTES = 65536  # T-01.1-10: header bytes only, never the whole file
IMAGE_RANGE = "bytes=0-65535"
IMAGE_WIDTH = 576  # card display width
RATIO_MIN, RATIO_MAX = 1.2, 4.0
IMAGE_MAX_TOTAL_BYTES = 1_000_000  # D-18: whole file, from content-range / content-length
MAX_PROBES = 6  # image requests per item, HF and README candidates together

# D-08 / T-01.2-10: README images come from one fixed host, for a repo parsed by
# this allowlist from the HF githubRepo URL.
RAW_BASE = RAW_IMAGE_HOST.rstrip("/")
README_MAX_BYTES = 262144
GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9-]{1,39})/([\w.-]{1,100}?)(?:\.git)?/?$"
)


class _RetryableStatus(Exception):
    def __init__(self, status: int):
        super().__init__(status)
        self.status = status


class EnrichError(Exception):
    """Non-fatal enrich problem. The message is a short reason code."""


def _get_json_once(client: httpx.Client, url: str) -> Any:
    resp = client.get(url)
    code = resp.status_code
    if code == 429 or code >= 500:
        raise _RetryableStatus(code)
    if code >= 400:
        raise EnrichError(f"http_{code}")
    return resp.json()


def _get_json(client: httpx.Client, url: str) -> Any:
    retrying = Retrying(
        stop=stop_after_attempt(ATTEMPTS),
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
        reraise=True,
    )
    try:
        return retrying(_get_json_once, client, url)
    except _RetryableStatus as e:
        raise EnrichError(f"http_{e.status}") from None


def valid_repo_id(rid: Any) -> bool:
    return isinstance(rid, str) and bool(REPO_ID_RE.fullmatch(rid)) and ".." not in rid


def _public_models(paper: dict) -> list[dict]:
    models = paper.get("linkedModels") or []
    return [m for m in models if isinstance(m, dict) and m.get("private") is not True]


def primary_model(paper: dict) -> str | None:
    """Highest-download non-private linked model with a valid id."""
    best: tuple[int, str] | None = None
    for m in _public_models(paper):
        rid = m.get("id")
        if not valid_repo_id(rid):
            continue
        dl = m.get("downloads")
        dl = dl if isinstance(dl, int) else 0
        if best is None or dl > best[0]:
            best = (dl, rid)
    return best[1] if best else None


def _spaces(paper: dict) -> list[str]:
    spaces = paper.get("linkedSpaces") or []
    return [s["id"] for s in spaces if isinstance(s, dict) and valid_repo_id(s.get("id"))]


def fmt_params(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B".replace(".0B", "B")
    return f"{round(n / 1e6)}M"


def _clip_id(s: str) -> str:
    return s if len(s) <= DATASET_ID_MAX else s[: DATASET_ID_MAX - 1] + "…"


def _datasets(model: dict) -> list[str]:
    card = model.get("cardData")
    ds: Any = card.get("datasets") if isinstance(card, dict) else None
    if isinstance(ds, str):
        ds = [ds]
    out = [d.strip() for d in ds or [] if isinstance(d, str) and d.strip()]
    if not out:
        tags = model.get("tags") or []
        out = [
            t.removeprefix("dataset:").strip()
            for t in tags
            if isinstance(t, str)
            and t.startswith("dataset:")
            and t.removeprefix("dataset:").strip()
        ]
    return out


def param_total(model: dict | None) -> int | None:
    if not isinstance(model, dict):
        return None
    st = model.get("safetensors")
    total = st.get("total") if isinstance(st, dict) else None
    if isinstance(total, int) and not isinstance(total, bool) and total > 0:
        return total
    return None


def facts(paper: dict, model: dict | None) -> dict[str, Any]:
    """Code rules for 크기 / 학습 데이터 / 공개 범위 plus the presence flags."""
    models = _public_models(paper)
    has_weights = bool(models)
    has_code = isinstance(paper.get("githubRepo"), str) and paper["githubRepo"].startswith(
        "https://"
    )
    spaces = _spaces(paper)
    has_demo = bool(spaces)

    parts = []
    if has_weights:
        gated = any(m.get("gated") not in (False, None) for m in models)
        parts.append("가중치(승인 필요)" if gated else "가중치")
    if has_code:
        parts.append("GitHub")
    if has_demo:
        parts.append("데모")
    release = " · ".join(parts) or UNKNOWN

    size = training = UNKNOWN
    total = param_total(model)
    if total is not None:
        size = f"{fmt_params(total)} 파라미터"
        if len(models) > 1:
            size += f" (외 {len(models) - 1}개 모델)"
    if isinstance(model, dict):
        ds = _datasets(model)
        if ds:
            training = ", ".join(_clip_id(d) for d in ds[:DATASET_SHOWN])
            if len(ds) > DATASET_SHOWN:
                training += f" 외 {len(ds) - DATASET_SHOWN}개"
    return {
        "size": size,
        "training_data": training,
        "release": release,
        "param_count": total,
        "has_weights": has_weights,
        "has_code": has_code,
        "has_demo": has_demo,
        "spaces": spaces,
    }


def _apply(item: Item, f: dict[str, Any], model_id: str | None) -> Item:
    evidence = list(item.model_info.evidence)
    if model_id:
        evidence.append(EvidenceLink(label="HF 모델", url=f"{HF_BASE}/{model_id}"))
    if f["spaces"]:
        evidence.append(EvidenceLink(label="HF 데모", url=f"{HF_BASE}/spaces/{f['spaces'][0]}"))
    info = item.model_info.model_copy(
        update={
            "size": f["size"],
            "training_data": f["training_data"],
            "release": f["release"],
            "evidence": evidence,
        }
    )
    # Pitfall 3: True when present, otherwise leave None. Never False.
    poc_update = {k: True for k in ("has_weights", "has_code", "has_demo") if f[k]}
    update: dict[str, Any] = {"model_info": info, "poc": item.poc.model_copy(update=poc_update)}
    if f["param_count"]:
        update["hardware"] = item.hardware.model_copy(update={"param_count": f["param_count"]})
    return item.model_copy(update=update)


_NON_FATAL = (httpx.HTTPError, EnrichError, ValueError, TypeError, KeyError)


def _reason(e: Exception) -> str:
    if isinstance(e, EnrichError):
        return str(e)
    return type(e).__name__


def _enrich_one(client: httpx.Client, item: Item) -> Item:
    rank = item.rank
    if not PAPER_ID_RE.fullmatch(item.paper_id):
        log.info("enrich=partial rank=%d reason=bad_paper_id", rank)
        return item
    try:
        paper = _get_json(client, f"{HF_BASE}/api/papers/{item.paper_id}")
        if not isinstance(paper, dict):
            raise EnrichError("bad_shape")
    except _NON_FATAL as e:
        log.info("enrich=partial rank=%d reason=%s", rank, _reason(e))
        return item

    model_id = primary_model(paper)
    model: dict | None = None
    reason: str | None = None
    if model_id:
        try:
            got = _get_json(client, f"{HF_BASE}/api/models/{model_id}?{MODEL_EXPAND}")
            model = got if isinstance(got, dict) else None
            if model is None:
                reason = "bad_shape"
        except _NON_FATAL as e:
            reason = _reason(e)
    try:
        out = _apply(item, facts(paper, model), model_id)
    except _NON_FATAL as e:
        log.info("enrich=partial rank=%d reason=%s", rank, _reason(e))
        return item
    if reason:
        log.info("enrich=partial rank=%d reason=%s", rank, reason)
    else:
        log.info("enrich=ok rank=%d", rank)
    return out


def hf_image_urls(media_urls: list[str] | None) -> list[str]:
    """HF-upload image URLs (png/jpg/jpeg/gif, case-insensitive), in order. Videos
    and other hosts are skipped (T-01.1-09)."""
    return [
        url
        for url in media_urls or []
        if isinstance(url, str) and url.startswith(IMAGE_HOST) and url.lower().endswith(IMAGE_EXTS)
    ]


def pick_image_url(media_urls: list[str] | None) -> str | None:
    """First HF-upload image URL, or None."""
    urls = hf_image_urls(media_urls)
    return urls[0] if urls else None


# ------------------------------------------------------------- README images


def parse_repo(github_url: Any) -> tuple[str, str] | None:
    """(owner, repo) from an https://github.com/{owner}/{repo} URL, else None."""
    if not isinstance(github_url, str):
        return None
    m = GITHUB_REPO_RE.fullmatch(github_url)
    if not m or ".." in github_url:
        return None
    return m.group(1), m.group(2)


_IMG_RE = re.compile(
    r"!\[[^\]]*\]\(\s*<?(?P<md>[^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
    r"|<img\b[^>]*?\bsrc\s*=\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
_BADGE_RE = re.compile(
    r"shields\.io|badge|/actions/workflows/|pepy\.tech|codecov|badgen|star-history|komarev",
    re.IGNORECASE,
)
_LOGO_RE = re.compile(r"logo|wordmark|lockup|emblem|icon|avatar", re.IGNORECASE)


# Markdown that never renders: HTML comments and fenced code blocks.
_HIDDEN_RE = re.compile(
    r"<!--.*?(?:-->|\Z)|^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[ \t]*$|\Z)",
    re.DOTALL | re.MULTILINE,
)
# github.com/{o}/{r}/(blob|raw)/{ref}/{path} -> raw.githubusercontent.com/{o}/{r}/{ref}/{path}
_GITHUB_FILE_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9-]{1,39})/([\w.-]{1,100})/(?:blob|raw)/(.+)$"
)
# D-18: hosts that redirect (302 to signed S3 / HF CDN) or expire. Not on
# IMAGE_HOSTS anyway; named here so a later allowlist change cannot let them in.
_REDIRECTING_RE = re.compile(
    r"^https://(?:github\.com/(?:user-attachments/|[^/]+/[^/]+/assets/)"
    r"|huggingface\.co/.*/resolve/"
    r"|private-user-images\.githubusercontent\.com/"
    r"|camo\.githubusercontent\.com/)",
    re.IGNORECASE,
)


def _resolve(src: str, owner: str, repo: str) -> str | None:
    """Absolute https URL for an image src, or None when it can never be used."""
    if not src or any(c.isspace() for c in src) or ".." in src:
        return None
    if "?" in src or "#" in src:  # Gmail proxy and signed URLs (Phase 1.1 A2)
        return None
    if src.startswith("//"):
        src = "https:" + src
    if "://" in src:
        if not src.startswith("https://"):
            return None
        m = _GITHUB_FILE_RE.match(src)
        if m:
            return f"{RAW_BASE}/{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return src
    if ":" in src.split("/", 1)[0]:  # data:, mailto: and other schemes
        return None
    path = src
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")
    if not path:
        return None
    return f"{RAW_BASE}/{owner}/{repo}/HEAD/{path}"


def _usable(url: str) -> bool:
    if _REDIRECTING_RE.match(url):
        return False
    if not url.startswith(IMAGE_HOSTS) or len(url) > IMAGE_URL_MAX:
        return False
    if "?" in url or "#" in url or ".." in url:
        return False
    if not url.lower().endswith(IMAGE_EXTS):
        return False
    if _BADGE_RE.search(url):
        return False
    return not _LOGO_RE.search(url.rsplit("/", 1)[-1])


def readme_candidates(md: str, owner: str, repo: str) -> list[str]:
    """Direct image URLs from a README in document order, deduplicated (D-08, D-18).

    Markdown `![alt](src "title")` and `<img src=...>` are read with regexes only;
    comments and fenced code are dropped first. Every result passes the v3
    ItemImage rule (IMAGE_HOSTS, at most IMAGE_URL_MAX, no query or fragment).
    """
    out: list[str] = []
    for m in _IMG_RE.finditer(_HIDDEN_RE.sub("", md)):
        raw = m.group("md") or m.group("dq") or m.group("sq") or m.group("bare") or ""
        url = _resolve(html.unescape(raw.strip()), owner, repo)
        if url and _usable(url) and url not in out:
            out.append(url)
    return out


def _read_readme(client: httpx.Client, owner: str, repo: str, rank: int) -> str | None:
    url = f"{RAW_BASE}/{owner}/{repo}/HEAD/README.md"
    try:
        with client.stream("GET", url, timeout=TIMEOUT, follow_redirects=False) as resp:
            if resp.status_code != 200:
                log.info("readme=none rank=%d reason=http_%d", rank, resp.status_code)
                return None
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) >= README_MAX_BYTES:
                    break
    except httpx.HTTPError as e:
        log.info("readme=none rank=%d reason=%s", rank, type(e).__name__)
        return None
    return bytes(buf[:README_MAX_BYTES]).decode("utf-8", errors="replace")


# ------------------------------------------------------------------- probing


class _NoImage(Exception):
    """The candidate is unusable. The message is a short reason code."""


_RANGE_TOTAL_RE = re.compile(r"^bytes \d+-\d+/(\d+)$")


def _total_bytes(resp: httpx.Response) -> int | None:
    if resp.status_code == 206:
        m = _RANGE_TOTAL_RE.match(resp.headers.get("content-range", "").strip())
        return int(m.group(1)) if m else None
    length = resp.headers.get("content-length", "").strip()
    return int(length) if length.isdigit() else None


def _read_head(client: httpx.Client, url: str) -> bytes:
    with client.stream(
        "GET", url, headers={"Range": IMAGE_RANGE}, timeout=TIMEOUT, follow_redirects=False
    ) as resp:
        code = resp.status_code
        if 300 <= code < 400:
            raise _NoImage("redirect")
        if code not in (200, 206):
            raise _NoImage(f"http_{code}")
        ctype = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype not in IMAGE_TYPES:
            raise _NoImage("content_type")
        total = _total_bytes(resp)
        if total is None:
            raise _NoImage("bytes_unknown")
        if total > IMAGE_MAX_TOTAL_BYTES:
            raise _NoImage("bytes")
        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf.extend(chunk)
            if len(buf) >= IMAGE_MAX_BYTES:
                break
    return bytes(buf[:IMAGE_MAX_BYTES])


def _dims(head: bytes) -> tuple[int, int]:
    # Header-only parse: Image.open reads the size without decoding pixels. Every
    # Pillow problem, including decompression-bomb warnings, means no image.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(head)) as im:
                w, h = im.size
    except Exception:  # noqa: BLE001 - any parse failure is "no image"
        raise _NoImage("decode") from None
    if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0):
        raise _NoImage("decode")
    return w, h


def _probe(client: httpx.Client, url: str) -> ItemImage:
    """One candidate through every filter. Raises _NoImage with a reason code."""
    try:
        w, h = _dims(_read_head(client, url))
        if w < IMAGE_WIDTH:
            raise _NoImage("width")
        if not RATIO_MIN <= w / h <= RATIO_MAX:
            raise _NoImage("ratio")
        return ItemImage(url=url, width=IMAGE_WIDTH, height=round(IMAGE_WIDTH * h / w))
    except (httpx.HTTPError, ValueError) as e:
        raise _NoImage(type(e).__name__) from None


class _Prober:
    """Probes candidates in order, at most MAX_PROBES per item."""

    def __init__(self, client: httpx.Client, rank: int):
        self.client = client
        self.rank = rank
        self.probes = 0
        self.reason = "no_candidate"

    def first(self, urls: list[str]) -> ItemImage | None:
        for url in urls:
            if self.probes >= MAX_PROBES:
                self.reason = "probe_limit"
                return None
            self.probes += 1
            try:
                return _probe(self.client, url)
            except _NoImage as e:
                self.reason = str(e)
                log.info("image=skip rank=%d reason=%s", self.rank, e)
        return None


def pick_image(
    client: httpx.Client,
    media_urls: list[str] | None,
    rank: int,
    github_url: str | None = None,
) -> ItemImage | None:
    """HF media images first, then README images (fetched only when needed)."""
    prober = _Prober(client, rank)
    image = prober.first(hf_image_urls(media_urls))
    if image is None and github_url and prober.probes < MAX_PROBES:
        repo = parse_repo(github_url)
        if repo is None:
            log.info("readme=none rank=%d reason=bad_repo", rank)
        else:
            md = _read_readme(client, *repo, rank)
            if md is not None:
                image = prober.first(readme_candidates(md, *repo))
    if image is None:
        log.info("image=none rank=%d reason=%s", rank, prober.reason)
        return None
    log.info("image=ok rank=%d", rank)
    return image


def enrich_items(
    items: list[Item], entries: list[HfEntry], *, client: httpx.Client | None = None
) -> list[Item]:
    """Fill code-owned model facts and the per-item image. Never raises for HF problems."""
    media = {e.paper.id: e.paper.mediaUrls for e in entries}
    repos = {e.paper.id: e.paper.githubRepo for e in entries}
    own = client is None
    if own:
        client = httpx.Client(timeout=TIMEOUT)  # same default User-Agent as fetch
    try:
        out = []
        for item in items:
            item = _enrich_one(client, item)
            image = pick_image(
                client, media.get(item.paper_id), item.rank, repos.get(item.paper_id)
            )
            out.append(item.model_copy(update={"image": image}))
        return out
    finally:
        if own:
            client.close()
