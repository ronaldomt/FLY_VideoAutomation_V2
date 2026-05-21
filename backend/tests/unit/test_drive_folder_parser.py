"""Drive folder URL → folder id parser. See CLAUDE.md §3 destination step."""

from __future__ import annotations

import pytest

from fly_backend.errors import BehaviorError
from fly_backend.integrations.composio_drive import parse_folder_id


@pytest.mark.parametrize(
    "input_url,expected_id",
    [
        (
            "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoP",
            "1aBcDeFgHiJkLmNoP",
        ),
        (
            "https://drive.google.com/drive/u/0/folders/1aBcDeFgHiJkLmNoP",
            "1aBcDeFgHiJkLmNoP",
        ),
        (
            "https://drive.google.com/open?id=1aBcDeFgHiJkLmNoP",
            "1aBcDeFgHiJkLmNoP",
        ),
        (
            "1aBcDeFgHiJkLmNoP",
            "1aBcDeFgHiJkLmNoP",
        ),
    ],
)
def test_parses_valid_inputs(input_url: str, expected_id: str) -> None:
    assert parse_folder_id(input_url) == expected_id


def test_rejects_empty_string() -> None:
    with pytest.raises(BehaviorError):
        parse_folder_id("")


def test_rejects_random_url() -> None:
    with pytest.raises(BehaviorError):
        parse_folder_id("https://example.com/whatever")
