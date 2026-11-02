"""SUBSCRIBERS_CSV decoding (DLVR-01)."""

import base64

import pytest

from newsletter.delivery.subscribers import Subscriber, load_subscribers, parse_subscribers
from newsletter.errors import NoSubscribersError

CSV = "email,name\nsubscriber@example.com,홍길동\n"
EXPECTED = [Subscriber("subscriber@example.com", "홍길동")]


def test_plain_text():
    assert load_subscribers(CSV) == EXPECTED


def test_leading_bom_character():
    assert load_subscribers("﻿" + CSV) == EXPECTED


def test_crlf_line_endings():
    assert load_subscribers(CSV.replace("\n", "\r\n")) == EXPECTED


def test_base64_utf8_bom_bytes():
    text = base64.b64encode(CSV.encode("utf-8-sig")).decode("ascii")
    assert load_subscribers(text) == EXPECTED


def test_base64_cp949_bytes():
    text = base64.b64encode(CSV.encode("cp949")).decode("ascii")
    assert load_subscribers(text) == EXPECTED


def test_base64_wrapped_across_lines():
    raw = base64.b64encode(CSV.encode("utf-8")).decode("ascii")
    wrapped = "\n".join(raw[i : i + 20] for i in range(0, len(raw), 20)) + "\n"
    assert load_subscribers(wrapped) == EXPECTED


def test_headers_are_stripped_and_lowercased():
    assert load_subscribers(" Email , NAME \nsubscriber@example.com,홍길동\n") == EXPECTED


def test_name_column_is_optional():
    assert load_subscribers("email\nsubscriber@example.com\n") == [
        Subscriber("subscriber@example.com", "")
    ]


def test_invalid_rows_skipped_and_counted():
    text = CSV + "not-an-email,김\n,빈칸\na@b,짧음\nx y@example.com,공백\n"
    subs, skipped = parse_subscribers(text)
    assert subs == EXPECTED
    assert skipped == 4


def test_duplicate_email_kept_once():
    text = CSV + "Subscriber@Example.com,중복\n"
    subs, skipped = parse_subscribers(text)
    assert subs == EXPECTED
    assert skipped == 1


def test_missing_email_column_raises_without_row_content():
    with pytest.raises(NoSubscribersError) as exc:
        load_subscribers("mail,name\nsubscriber@example.com,홍길동\n")
    assert "@" not in str(exc.value)
    assert "홍길동" not in str(exc.value)


def test_zero_valid_rows_raises_with_counts_only():
    with pytest.raises(NoSubscribersError) as exc:
        load_subscribers("email,name\nnot-an-email,홍길동\n")
    msg = str(exc.value)
    assert "not-an-email" not in msg
    assert "홍길동" not in msg
    assert "1" in msg


@pytest.mark.parametrize("text", ["", "   ", "﻿", "email,name\n"])
def test_empty_input_raises(text):
    with pytest.raises(NoSubscribersError):
        load_subscribers(text)
