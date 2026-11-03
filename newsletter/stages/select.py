"""Deterministic Top-N selection by GitHub stars (COLL-05, D-02, D-03).

Repo papers rank by HF `paper.githubStars` (read from the daily_papers payload
only; no GitHub API call, D-15). N is the count of repo papers with at least
STAR_MIN stars, clamped to N_MIN..N_MAX. When the week has fewer than N repo
papers, the rest is filled by the upvote order (`sort_key`).
"""

from newsletter.schema import HfEntry

STAR_MIN = 100
N_MIN = 3
N_MAX = 10


def sort_key(entry: HfEntry) -> tuple:
    """Upvote order, used for the fill path."""
    return (
        -entry.paper.upvotes,
        -entry.numComments,
        entry.paper.submittedOnDailyAt,
        entry.paper.id,
    )


def has_repo(entry: HfEntry) -> bool:
    repo = entry.paper.githubRepo
    return isinstance(repo, str) and repo.startswith("https://")


def stars(entry: HfEntry) -> int | None:
    """githubStars when it is a real non-negative int, else None (untrusted input)."""
    s = entry.paper.githubStars
    if isinstance(s, int) and not isinstance(s, bool) and s >= 0:
        return s
    return None


def star_key(entry: HfEntry) -> tuple:
    s = stars(entry)
    return (
        -(s if s is not None else -1),  # missing stars sort after 0
        -entry.paper.upvotes,
        -entry.numComments,
        entry.paper.submittedOnDailyAt,
        entry.paper.id,
    )


def select_top(entries: list[HfEntry]) -> list[HfEntry]:
    repos = sorted((e for e in entries if has_repo(e)), key=star_key)
    n_star = sum(1 for e in repos if (stars(e) or 0) >= STAR_MIN)
    n = min(max(n_star, N_MIN), N_MAX)
    picked = repos[:n]
    if len(picked) < n:
        others = sorted((e for e in entries if not has_repo(e)), key=sort_key)
        picked += others[: n - len(picked)]
    return picked
