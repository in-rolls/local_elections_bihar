"""Result-to-candidate matching on shapes seen in the SEC feeds."""

from matching import match, name_key


def test_swapped_serials_follow_names():
    # d33 ward seat: candidate list in name order, results in ballot order.
    listed = {1: "उपेन्द्र मिस्त्री", 2: "कमल देव सिंह", 3: "जबार अंसारी"}
    results = {1: " जबार अंसारी", 2: " कमल देव सिंह (विजेता)", 3: " उपेन्द्र मिस्त्री"}
    assert match(listed, results) == {
        1: (3, "name"),
        2: (2, "serial_and_name"),
        3: (1, "name"),
    }


def test_numbered_duplicates_and_honorifics():
    listed = {1: "आशा देवी", 2: "आशा देवी", 3: "मो0 सऊद"}
    results = {1: " आशा देवी 1", 2: " आशा देवी 2 (विजेता)", 3: "मो० सऊद"}
    assert {s: m for s, (_, m) in match(listed, results).items()} == {
        1: "serial_and_name",
        2: "serial_and_name",
        3: "serial_and_name",
    }
    assert name_key("श्रीमती  रूबी  देवी") == name_key("रूबी देवी")


def test_unlisted_title_contained_and_result_only():
    listed = {1: "नीतू कुमारी", 2: "निगारे इशरत"}
    results = {1: "नीतू कुमारी", 2: "विवी निगारे इशरत", 3: "सोनी देवी (विजेता)"}
    assert match(listed, results) == {
        1: (1, "serial_and_name"),
        2: (2, "name_contained"),
        3: (None, "result_only"),
    }


def test_same_serial_kept_only_when_no_name_matches():
    listed = {1: "पुनम देवी", 2: "सीता देवी"}
    results = {1: "पूनम देवी", 2: "सीता देवी"}
    assert match(listed, results)[1] == (1, "serial_only")
