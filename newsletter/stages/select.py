"""Deterministic Top-N selection (D-10)."""

from newsletter.schema import HfEntry


def sort_key(entry: HfEntry) -> tuple:
    return (
        -entry.paper.upvotes,
        -entry.numComments,
        entry.paper.submittedOnDailyAt,
        entry.paper.id,
    )


def select_top(entries: list[HfEntry], n: int = 10) -> list[HfEntry]:
    return sorted(entries, key=sort_key)[:n]
