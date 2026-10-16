"""Cross-election GP linkage on name shapes seen in the 2016 and 2021 rosters."""

import pandas as pd
from preclink import ExactComparison

from local_elections_bihar.linkage.mukhiya import PlaceName, fold, link, name_key


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
