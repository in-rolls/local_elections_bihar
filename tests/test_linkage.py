"""Cross-election GP linkage on name shapes seen in the 2016 and 2021 rosters."""

import pandas as pd
from preclink import ExactComparison

from local_elections_bihar.linkage.mukhiya import (
    PlaceName,
    english_key,
    fold,
    hindi_key,
    link,
    link_in_learned_blocks,
    name_key,
    romanized_key,
)


def frame(rows):
    out = pd.DataFrame(rows, columns=["key", "native", "latin", "wards"])
    out["district_code"], out["block_code"] = "29", "014"
    out["name_key"] = [
        name_key(n, r) for n, r in zip(out["native"], out["latin"], strict=True)
    ]
    return out


def test_fold_absorbs_romanization_variants():
    assert fold("03 - SHANKARDIH") == fold("shankardeeh")
    assert fold("Bhagwatpur") == fold("bhagvatpur")
    assert fold("Phoolwariya") == fold("fulvariya")


def test_numbers_and_directions_come_from_the_printed_name():
    assert name_key("दरियापुर-२", "dariyapurag")[1] == {2}
    assert name_key("10 - Rani -01", "10 - Rani -01")[1] == {1}
    assert name_key("सनहा पूर्वी", "sanha purvi")[2] == {"east"}


def test_sibling_gps_with_different_numbers_never_pair():
    left = frame([("a", "Dariyapur-1", "Dariyapur-1", 15)])
    right = frame([("x", "दरियापुर-2", "dariyapurag", 11)])
    assert link(left, right, ["block_code"], [PlaceName()], 0.5).empty


def test_one_to_one_assignment_prefers_the_closer_name():
    left = frame([("a", "Sedhan", "Sedhan", 11), ("b", "Jethwar", "Jethwar", 12)])
    right = frame([("x", "जेठवार", "jethwar", 12), ("y", "सेदहा", "sedaha", 11)])
    pairs = link(left, right, ["block_code"], [PlaceName()], 0.6)
    assert dict(zip(pairs["left"], pairs["right"], strict=True)) == {"a": "y", "b": "x"}


def test_ward_pass_needs_equal_ward_counts():
    left = frame([("a", "Parham", "Parham", 13)])
    agree = frame([("x", "पड़हम", "padaham", 13)])
    differ = frame([("x", "पड़हम", "padaham", 9)])
    comparisons = [PlaceName(), ExactComparison("wards")]
    assert len(link(left, agree, ["block_code"], comparisons, 0.8)) == 1
    assert link(left, differ, ["block_code"], comparisons, 0.8).empty


def test_qualifiers_conflict_only_within_a_family():
    from local_elections_bihar.linkage.mukhiya import qualifiers_conflict

    south = name_key("SINGHIYA BUJURG DAKSHANI", "singhiya bujurg dakshani")[2]
    assert south == {"buzurg", "south"}
    assert not qualifiers_conflict(south, name_key("सिंघिया बुजुर्ग दक्षिण", "")[2])
    assert qualifiers_conflict(south, name_key("सिंघिया बुजुर्ग उत् तर", "")[2])
    assert not qualifiers_conflict(frozenset({"kalan"}), frozenset({"north"}))
    assert qualifiers_conflict(frozenset({"kalan"}), frozenset({"khurd"}))


def test_english_and_hindi_compass_words_meet():
    # Sharan's file writes the compass word in English, in brackets, or as a
    # letter; the 2006 workbooks print the Hindi word or its abbreviation.
    assert english_key("SARISAW PAHI (E)") == hindi_key(
        "सरिसवपाही पूर्वी", "sarisavpahi purvi"
    )
    assert english_key("PAROO [N]") == hindi_key("पारू उत्तरी", "paru uttari")
    assert english_key("NORTHI PATJIRAWA")[2] == {"north"}
    # प0 is romanized "0v"; the word is dropped by position and is not a number
    assert hindi_key("प0 वाखरपुर", "0v vakharpur") == (
        fold("vakharpur"),
        frozenset(),
        {"west"},
    )
    assert english_key("FULWARIA-II")[1] == hindi_key("फुलवरिया-2", "phulwariya")[1]


def test_opposite_compass_words_never_pair():
    left = frame([("a", "x", "x", 1)])
    right = frame([("x", "x", "x", 1)])
    left["name_key"] = [english_key("SAKRI EAST")]
    right["name_key"] = [hindi_key("सकरी पश्चिमी", "sakri pashchimi")]
    assert link(left, right, ["block_code"], [PlaceName()], 0.5).empty
    right["name_key"] = [hindi_key("सकरी पूर्वी", "sakri purvi")]
    assert len(link(left, right, ["block_code"], [PlaceName()], 0.5)) == 1


def test_romanized_compass_words_meet_english_ones():
    # the 2016 form prints the Hindi word in Latin letters
    assert romanized_key("05 - Siswa Pashchimi") == english_key("SISWA WEST")
    assert romanized_key("RAGHUNATHPUR  DAKSHIN") == english_key("RAGHUNATHPUR SOUTH")
    assert romanized_key("Dakshini Madhubani")[2] == {"south"}
    assert romanized_key("03 - Dariyapur-2")[1] == {2}


def test_blocks_are_learned_before_names_are_paired():
    # Rampur recurs in both blocks; only the block tells the two apart.
    names = ["Rampur", "Belwa", "Chikani", "Rampur", "Kurma", "Satha"]
    coded = pd.DataFrame(
        {
            "key": list("abcdef"),
            "district_code": "07",
            "block_code": ["001"] * 3 + ["002"] * 3,
            "name_key": [romanized_key(n) for n in names],
        }
    )
    free = pd.DataFrame(
        {
            "key": [1, 2, 3, 4, 5, 6],
            "district_code": "07",
            "block_name": ["NORTH BLOCK"] * 3 + ["SOUTH BLOCK"] * 3,
            "name_key": [english_key(n.upper()) for n in names],
        }
    )
    pairs = link_in_learned_blocks(coded, free)
    assert dict(zip(pairs["left"], pairs["right"], strict=True)) == dict(
        zip("abcdef", [1, 2, 3, 4, 5, 6], strict=True)
    )
    assert set(pairs["link_pass"]) == {"block"}
