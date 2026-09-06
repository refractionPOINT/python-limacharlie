"""The table and CSV renderers must not hand terminal control sequences to a terminal.

The CLI prints values it did not author: `limacharlie mailsec message list` renders
email subjects, sender display names, attachment filenames and URLs -- all chosen by
whoever sent the mail -- and `limacharlie search` renders event fields the same way.
A terminal treats ESC-[ sequences in that text as commands rather than data.

JSON and YAML already escape these; these tests pin that the table and CSV paths do
too, and that the escaping is a rendering change only (JSON is untouched).
"""

import json

import pytest

from limacharlie.output import (
    escape_control_chars,
    format_csv,
    format_json,
    format_table,
    set_wide_mode,
)

# A subject that clears the screen, then repaints a fake row, then hides the rest.
HOSTILE_SUBJECT = "\x1b[2J\x1b[1;1HInvoice paid\rDELETED\x07\x1b[8m"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param([{"subject": HOSTILE_SUBJECT, "from": "a@b.example"}], id="list-of-dicts"),
        pytest.param([HOSTILE_SUBJECT], id="list-of-primitives"),
        pytest.param({"subject": HOSTILE_SUBJECT}, id="single-record"),
        pytest.param({"m1": {"subject": HOSTILE_SUBJECT}, "m2": {"subject": "ok"}}, id="dict-of-dicts"),
        pytest.param({"links": [HOSTILE_SUBJECT]}, id="short-list-cell"),
        pytest.param(HOSTILE_SUBJECT, id="bare-string"),
    ],
)
def test_table_never_emits_a_raw_escape(data):
    out = format_table(data)
    for ch in ("\x1b", "\r", "\x07"):
        assert ch not in out, f"{ch!r} survived into table output: {out!r}"
    # The text is still there to read, just inert. (Checked in wide mode: the default
    # narrow cell truncates on terminal width, and an escaped sequence is wider than the
    # raw one it replaces, which is the price of rendering it visibly.)
    set_wide_mode(True)
    try:
        wide = format_table(data)
    finally:
        set_wide_mode(False)
    assert "Invoice paid" in wide
    assert "\x1b" not in wide


def test_csv_never_emits_a_raw_escape():
    out = format_csv([{"subject": HOSTILE_SUBJECT}])
    assert "\x1b" not in out
    assert "\x07" not in out
    # csv's own line terminator is \r\n, so a bare \r from the VALUE is what must be gone:
    # the value's cell must not contain one.
    value_cell = out.split("\r\n", 1)[1]
    assert "\r" not in value_cell


def test_c1_introducers_are_escaped_too():
    """Stripping only ESC leaves the same capability behind in 8-bit form."""
    out = format_table([{"subject": "a\x9b2Jb"}])
    assert "\x9b" not in out
    assert "\\x9b" in out


def test_tab_survives_but_newline_does_not():
    assert escape_control_chars("a\tb") == "a\tb"
    assert "\n" not in escape_control_chars("a\nb")


ESC = chr(27)
C1_CSI = chr(0x9B)


def test_column_names_are_escaped_too():
    """The header is a row. For a `limacharlie search` result the column names are the keys of
    an adapter-ingested event body, which the sender chose."""
    out = format_table([{"su" + ESC + "[2Jbject": "v", "ok": "w"}])
    assert ESC not in out
    out = format_table({"fi" + ESC + "[2Jeld": "v"})
    assert ESC not in out


def test_csv_header_row_is_escaped():
    out = format_csv([{"he" + ESC + "[2Jad": "v"}])
    assert ESC not in out
    # The row still lines up with its (escaped) header.
    header, row = out.split("\r\n")[:2]
    assert row == "v"
    assert "\\x1b" in header


def test_csv_of_a_bare_string_is_escaped():
    """Reached by `--filter 'messages[0].subject' --output csv`."""
    assert ESC not in format_csv(ESC + "[2JPWNED")


def test_c1_survives_json_encoding_so_dict_cells_need_escaping_too():
    """orjson and the stdlib both emit C1 verbatim; JSON only escapes C0.

    A dict or list cell goes through the JSON encoder, so without a second pass it would be
    the documented bypass of the C1 escaping this module adds.
    """
    out = format_table([{"payload": {"x": "p" + C1_CSI + "2Jq"}}])
    assert C1_CSI not in out
    set_wide_mode(True)
    try:
        assert C1_CSI not in format_table([{"payload": {"x": "p" + C1_CSI + "2Jq"}}])
    finally:
        set_wide_mode(False)
    assert C1_CSI not in format_csv([{"payload": {"x": "p" + C1_CSI + "2Jq"}}])


def test_json_output_is_unchanged():
    """The escaping is a TABLE/CSV rendering concern; machine output must not gain it."""
    out = format_json([{"subject": HOSTILE_SUBJECT}])
    assert json.loads(out)[0]["subject"] == HOSTILE_SUBJECT


def test_ordinary_text_is_untouched():
    """A renderer that mangled normal output would be worse than the hole it closes."""
    subject = "Re: Q3 forecast — 15% up (draft v2) café/naïve"
    assert escape_control_chars(subject) == subject
    set_wide_mode(True)
    try:
        assert subject in format_table([{"subject": subject, "score": 71}])
    finally:
        set_wide_mode(False)
