"""Greeting normalization (DLVR-02)."""

import pytest

from newsletter.delivery.subscribers import display_name
from newsletter.stages.render import render_html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("홍길동", "홍길동님"),
        ("홍길동님", "홍길동님"),
        (" 홍길동 님 ", "홍길동님"),
        ("", "구독자님"),
        (None, "구독자님"),
        ("  ", "구독자님"),
        ("님", "구독자님"),
        ("\t홍길동\x00", "홍길동님"),
    ],
)
def test_display_name(raw, expected):
    assert display_name(raw) == expected


def test_control_characters_removed():
    out = display_name("a\r\nb")
    assert "\r" not in out and "\n" not in out
    assert out == "ab님"


def test_markup_in_name_is_escaped_in_html(issue_w44):
    html = render_html(issue_w44, display_name("<b>x</b>"))
    assert "&lt;b&gt;" in html
    assert "<b>x</b>" not in html
