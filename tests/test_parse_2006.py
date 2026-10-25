"""Reading the 2006 SEC workbooks: reservation cells, headings, profiles."""

import pytest

from local_elections_bihar.parse.members_2006 import reserved_caste, reserved_woman
from local_elections_bihar.parse.sec_workbooks import Context, decode
from local_elections_bihar.parse.winners_2006 import age, winner_caste


@pytest.mark.parametrize(
    ("printed", "caste"),
    [
        ("अनारक्षित", "NONE"),
        ("अना0", "NONE"),
        ("अनारिक्षत", "NONE"),
        ("सामान्य", "NONE"),
        ("अनु0 जाति", "SC"),
        ("अ0 जा0", "SC"),
        ("आरक्षित ;अनु0 जातिद्ध", "SC"),
        ("अनुसूचित जन जाति", "ST"),
        ("अ0 ज0 जा0", "ST"),
        ("आरक्षित ;अनु0 ज0 जा0द्ध", "ST"),
        ("पि0 वर्ग", "BC"),
        ("पिछड़ी जाति", "BC"),
        ("आर0 पि0 वर्ग", "BC"),
        # too little to tell, or two categories at once
        ("आरक्षित", None),
        ("अनु0", None),
        ("----", None),
        ("अनारक्षित अनु0 जाति", None),
        ("अना0 पि0 वर्ग", None),
    ],
)
def test_the_seat_category_is_read_from_its_printed_cell(printed, caste):
    assert reserved_caste(printed) == caste


@pytest.mark.parametrize(
    ("printed", "woman"),
    [("महिला", 1), ("मलिा", 1), ("अन्य", 0), ("पुरूष", 0), ("----", None), (None, None)],
)
def test_the_womans_seat_is_read_from_its_cell(printed, woman):
    assert reserved_woman(printed) == woman


def test_headings_set_district_block_and_panchayat():
    context = Context()
    assert context.update(["जिला - गया"])
    assert context.update(["प्रखंड - बोधगया", None, "ग्राम कचहरी - नावाँ"])
    assert (context.district, context.block, context.gram_panchayat) == (
        "गया",
        "बोधगया",
        "नावाँ",
    )
    # a later block heading clears the panchayat
    context.update(["प्रखंड - मानपुर"])
    assert context.gram_panchayat is None


@pytest.mark.parametrize(
    "row",
    [
        [None, "जिला का नाम:", "अररिया"],
        ["जिला का नाम शेखपुरा"],
    ],
)
def test_profile_headings_with_or_without_a_colon(row):
    context = Context()
    context.update(row)
    assert context.district in {"अररिया", "शेखपुरा"}


def test_a_title_is_not_a_heading():
    assert not Context().update(["पंचायत निर्वाचन, 2006"])


@pytest.mark.parametrize(
    ("kruti", "unicode"),
    [
        ("xkso/Zu ;kno", "गोवर्धन यादव"),  # reph typed after a half form
        ("lkfo=kh nsoh", "सावित्री देवी"),  # stray stroke before ी
        ("lkfo=h nsoh", "सावित्री देवी"),
        ("lqfe=k nsoh", "सुमित्रा देवी"),  # a real ा is kept
    ],
)
def test_kruti_typing_variants(kruti, unicode):
    assert decode(kruti) == (unicode, kruti)


def test_an_undecodable_cell_keeps_its_bytes():
    assert decode("Ên; iz0 flag") == (None, "Ên; iz0 flag")


@pytest.mark.parametrize(
    ("printed", "caste"),
    [
        ("पिछड़ा वर्ग", "BC"),
        ("अत्यन्त पिछड़ा वर्ग", "EBC"),
        ("अ0 पि0 वर्ग", "EBC"),
        ("अनु0 जाति", "SC"),
        ("अनु0 जन जाति", "ST"),
        ("सामान्य", "NONE"),
        ("यादव", None),  # a jati, not a category
        ("अन्य", None),
    ],
)
def test_the_winners_own_category(printed, caste):
    assert winner_caste(printed) == caste


def test_a_printed_zero_age_is_unknown():
    assert age("0") is None
    assert age("45") == 45
