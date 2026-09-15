"""Synthetic source contracts for the non-mukhiya 2021 offices; no live requests."""

import offices_2021


def seat(post, seat_no, panchayat_id=None, block_id=1):
    u = {
        "post_id": post,
        "district_id": 33,
        "block_id": block_id,
        "panchayat_id": panchayat_id,
        "seat_no": seat_no,
        "district": "D",
        "block": "B",
        "panchayat": None,
    }
    return {**u, "unit_id": offices_2021.unit_id(u)}


def test_request_parameters_follow_portal_form():
    assert offices_2021.request_params(seat(1, 7, 12)) == {
        "postId": 1,
        "districtId": 33,
        "blockId": 1,
        "panchayatId": 12,
        "ward": 7,
        "psn": -1,
        "jpn": -1,
    }
    zila = seat(6, 3, block_id=None)
    assert offices_2021.request_params(zila)["blockId"] == ""
    assert offices_2021.request_params(zila)["jpn"] == 3
    assert zila["unit_id"] == "d33_z3"
