"""Reading Madhubani's 2006 result notices (प्रपत्र-23)."""

import collections

import pytest

from local_elections_bihar.parse import result_notices_2006 as notices


@pytest.mark.parametrize(
    ("line", "post", "caste", "woman", "name"),
    [
        (
            "1 उषा देवी मुखिया अनारक्षित महिला ग्रा0पं0वररी प्रा0नि0क्षे0सं0-1",
            "मुखिया",
            "अनारक्षित",
            "महिला",
            "उषा देवी",
        ),
        # a winner surnamed मुखिया is a member, not a mukhiya
        (
            "17 बुधन मुखिया (निर्विरोध) सदस्य अनारक्षित अन्य ग्रा0 पं0 रहिका प्रा0नि0क्षे0सं0-16",
            "सदस्य",
            "अनारक्षित",
            "अन्य",
            "बुधन मुखिया (निर्विरोध)",
        ),
        # the serial printed on a line of its own
        (
            "वीभा देवी मुखिया पिछड़ा वर्ग महिला ग्रा0 पं0 रहिका प्रा0नि0क्षे0सं0-2",
            "मुखिया",
            "पिछड़ा वर्ग",
            "महिला",
            "वीभा देवी",
        ),
    ],
)
def test_a_row_is_read_from_its_right_end(line, post, caste, woman, name):
    match = notices.ROW.match(line)
    assert (match["post"], match["caste"], match["woman"], match["name"]) == (
        post,
        caste,
        woman,
        name,
    )


@pytest.mark.parametrize(
    ("place", "body", "name"),
    [
        ("ग्रा0 पं0 समदा प्रा0नि0क्षे0सं0-1", "पं0", "समदा"),
        ("गा्र0 क0 करियौत प्रा0नि0क्षे0सं0-3", "क0", "करियौत"),
        ("ग्रा0 कचहरी बरही", "कचहरी", "बरही"),
        ("ग्र0 पं0 दतुआर प्रा0नि0क्षे0सं0-4", "पं0", "दतुआर"),
    ],
)
def test_the_place_column_names_the_body_and_panchayat(place, body, name):
    match = notices.PANCHAYAT.search(place)
    assert (match["body"], match["name"]) == (body, name)


@pytest.fixture(scope="module")
def rows():
    return notices.rows()


def test_madhubani_mukhiya_seats_carry_their_reservation(rows):
    mukhiya = [r for r in rows if r["office"] == "mukhiya"]
    # the SEC's profile workbook lists 398 Madhubani mukhiyas
    assert 385 <= len(mukhiya) <= 398
    assert all(r["reserved_woman"] in (0, 1) for r in mukhiya)
    assert sum(r["reserved_caste"] is None for r in mukhiya) == 0
    blocks = collections.Counter(r["block"] for r in mukhiya)
    assert len(blocks) == 21 and None not in blocks
