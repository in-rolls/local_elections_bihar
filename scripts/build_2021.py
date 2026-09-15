"""Build the validated 2021 panchayat release for all six offices from saved responses.

Reads only archives of saved SEC responses (no network). Every source field is
either mapped to a typed column or listed in EXCLUDED with a reason; an unknown
field stops the build, so a portal change cannot silently drop data.
"""

import argparse
import base64
import collections
import csv
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
from matching import match
from schemas_2021 import TABLES, dictionary_rows, polars_schema
from sec_portal import completed_bytes, decode_records

PHASE = "2021_1"
WINNER_MARK = re.compile(r"\s*\(विजेता\)\s*$")
EXCLUDED = {"MobileNo": "personal phone number; kept only in the raw archive"}
GENDER = {"पुरुष": "male", "महिला": "female", "अन्य": "other"}
CANDIDATE_FIELDS = {
    "PostId": "post_id",
    "OrderBy": "candidate_serial",
    "CandidateName": "candidate_name",
    "GaurdianName": "guardian_name",
    "Age": "candidate_age",
    "Gender": "candidate_gender_raw",
    "CandidateAddress": "candidate_address",
    "SymbolName": "symbol_name",
    "SymbolUrl": "symbol_file",
    "CandidatePhoto": "photo_url",
    "CandidateDoc": "affidavit_url",
}
RESULT_FIELDS = {
    "SlNo": "result_record_id",
    "PostName": "post_name",
    "Dist": "result_district_id",
    "DistrictName": "result_district",
    "BlockID": "result_block_id",
    "BlockName": "result_block",
    "PanchayatNo": "result_panchayat_id",
    "PanchayatName": "result_panchayat",
    "WardNo": "result_seat_no",
    "OrderBy": "result_serial",
    "CandidateName": "result_name",
    "TotalVote": "votes",
    "IsWin": "elected",
}
CURRENT_FIELDS = {
    "Dist": "district_id",
    "BlockID": "block_id",
    "PanchayatNo": "panchayat_id",
    "WardNo": "seat_no",
    "District": "district",
    "Block": "block",
    "Panchayat": "panchayat",
    "Post": "post_name",
    "CandidateName": "candidate_name",
    "GuardianName": "guardian_name",
    "Gender": "candidate_gender_raw",
    "Age": "candidate_age",
    "Address": "candidate_address",
    "Category": "candidate_category",
    "ReservationFor": "reservation_for_reported",
    "ReservationStatus": "reservation_status_reported",
    "CandidatePhotos": "photo_url",
    "Affidavit": "affidavit_url",
    "Reservation": "seat_reservation",
}
INTEGERS = {
    "post_id",
    "candidate_serial",
    "candidate_age",
    "result_record_id",
    "result_district_id",
    "result_block_id",
    "result_panchayat_id",
    "result_seat_no",
    "result_serial",
    "votes",
    "district_id",
    "block_id",
    "panchayat_id",
    "seat_no",
}


def as_int(value, name):
    if value is None or value in ("", "NA"):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Boolean where an integer was expected: {name}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    raise ValueError(f"Unexpected value for {name}: {value!r}")


def typed(row, fields, where):
    unknown = set(row) - set(fields) - set(EXCLUDED)
    if unknown:
        raise ValueError(f"Unmapped source fields {sorted(unknown)} in {where}")
    out = {}
    for source, column in fields.items():
        if source not in row:
            continue
        value = row[source]
        if column in INTEGERS:
            value = as_int(value, source)
        elif column == "elected":
            if not isinstance(value, bool):
                raise ValueError(f"IsWin is not boolean in {where}: {value!r}")
        elif value is not None and not isinstance(value, str):
            raise ValueError(f"{source} is not text in {where}: {value!r}")
        out[column] = None if value == "" else value
    return out


class Responses:
    """Finished request events from tar archives, keyed by ledger path."""

    def __init__(self, archives):
        self.events, self.archives = {}, {}
        for path in archives:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            self.archives[path.name] = digest.hexdigest()
            with tarfile.open(path) as tar:
                for member in tar:
                    name = member.name.removeprefix("./")
                    base = name.rsplit("/", 1)[-1]
                    if not name.endswith(".jsonl.gz") or base.startswith("._"):
                        continue
                    event = completed_bytes(tar.extractfile(member).read())
                    if event is not None:
                        self.events[name.removesuffix(".jsonl.gz")] = event

    def records(self, key):
        event = self.events.get(key)
        if event is None:
            return None, None, None
        body = base64.b64decode(event["body_base64"])
        return event, hashlib.sha256(body).hexdigest(), decode_records(body)


def mukhiya_frame(archive):
    with tarfile.open(archive) as tar:
        member = tar.getmember("2021/frame.parquet")
        rows = pq.read_table(io.BytesIO(tar.extractfile(member).read())).to_pylist()
    return [
        {
            "post_id": 3,
            "district_id": r["district_id"],
            "block_id": r["block_id"],
            "panchayat_id": int(r["panchayat_id"]),
            "seat_no": None,
            "unit_id": "d{}_b{}_p{}".format(
                r["district_id"], r["block_id"], int(r["panchayat_id"])
            ),
            "district": r["district"],
            "block": r["block"],
            "panchayat": r["panchayat"],
        }
        for r in rows
    ]


def ledger_key(u, kind):
    if u.get("phase"):
        return f"byelections/{u['phase']}/p{u['post_id']}/{kind}/{u['unit_id']}"
    if u["post_id"] == 3:
        return f"2021/{kind}/{u['unit_id']}"
    return f"2021/offices/p{u['post_id']}/{kind}/{u['unit_id']}"


def check_seat(u, r, where):
    got = (
        r["result_district_id"],
        r.get("result_block_id"),
        r.get("result_panchayat_id"),
        r.get("result_seat_no"),
    )
    post, d, b, p, s = (
        u[k] for k in ("post_id", "district_id", "block_id", "panchayat_id", "seat_no")
    )
    ok = got[0] == d and (
        (post in (1, 2) and got[1:] == (b, p, s))
        or (post in (3, 4) and got[1:3] == (b, p))
        or (post == 5 and got[1] == b and got[3] == s)
        or (post == 6 and got[3] == s)
    )
    if not ok:
        raise ValueError(f"Result outside requested seat {where}: {got}")


def build_post(units, responses):
    seats, candidates, results, winners = [], [], [], []
    for u in units:
        phase = u.get("phase") or PHASE
        where = f"{phase} p{u['post_id']} {u['unit_id']}"
        _, _, phases = responses.records(ledger_key(u, "phases"))
        c_event, c_sha, c_rows = responses.records(ledger_key(u, "candidates"))
        r_event, r_sha, r_rows = responses.records(ledger_key(u, "results"))
        for event in (c_event, r_event):
            if event is not None and event["params"]["phase"] != phase:
                raise ValueError(f"Unexpected election phase in {where}")
        listed = []
        for i, row in enumerate(c_rows or [], 1):
            t = typed(row, CANDIDATE_FIELDS, where)
            if t.pop("post_id") != u["post_id"]:
                raise ValueError(f"Candidate office differs from request in {where}")
            gender = GENDER.get((t["candidate_gender_raw"] or "").strip())
            if gender is None:
                raise ValueError(
                    f"Unknown gender {t['candidate_gender_raw']!r} {where}"
                )
            age = t["candidate_age"]
            listed.append(
                {
                    "post_id": u["post_id"],
                    "unit_id": u["unit_id"],
                    "in_candidate_list": True,
                    **t,
                    "candidate_gender": gender,
                    "candidate_age_implausible": age is not None
                    and not 21 <= age <= 100,
                    "source_url": c_event["url"],
                    "fetched_at": c_event["fetched_at"],
                    "source_sha256": c_sha,
                    "source_row": i,
                }
            )
        reported = []
        for i, row in enumerate(r_rows or [], 1):
            t = typed(row, RESULT_FIELDS, where)
            check_seat(u, t, where)
            reported.append(
                {
                    "post_id": u["post_id"],
                    "unit_id": u["unit_id"],
                    **t,
                    "source_url": r_event["url"],
                    "fetched_at": r_event["fetched_at"],
                    "source_sha256": r_sha,
                    "source_row": i,
                }
            )
        # 16,113 ward-member result rows have no OrderBy; they are keyed by their
        # position (a negative number never equal to a list serial) and matched by
        # name, so candidates without a serial are never pooled together.
        for r in reported:
            r["_key"] = (
                r["result_serial"]
                if r["result_serial"] is not None
                else -r["source_row"]
            )
        names = {c["candidate_serial"]: c["candidate_name"] for c in listed}
        result_names, first_row = {}, {}
        for r in reported:
            result_names.setdefault(r["_key"], r["result_name"])
            first_row.setdefault(r["_key"], r)
        pairs = match(names, result_names)
        votes, flags = collections.Counter(), collections.defaultdict(set)
        for r in reported:
            serial, method = pairs[r["_key"]]
            r["candidate_serial"] = serial
            r["match_method"] = None if serial is None else method
            if r["votes"] is not None:
                votes[r["_key"]] += r["votes"]
            flags[r["_key"]].add(r["elected"])
        # In a few split seats IsWin is set on only some of the winner's panchayat
        # rows (4 samiti seats in district 2); the seat-level flag is any row.
        partial = any(len(f) > 1 for f in flags.values())
        by_candidate = {
            serial: (key, method)
            for key, (serial, method) in pairs.items()
            if serial is not None
        }
        for c in listed:
            if not c["in_candidate_list"]:
                continue
            key, method = by_candidate.get(c["candidate_serial"], (None, None))
            present = key is not None
            c.update(
                result_present=present,
                result_serial=first_row[key]["result_serial"] if present else None,
                match_method=method,
                votes=votes[key] if present else None,
                elected=(True in flags[key]) if present else None,
            )
        # Result-only candidates: named in results but absent from the candidate list
        # (e.g. 1,814 samiti candidates); kept so candidates covers every contestant.
        for key, (serial, _) in pairs.items():
            if serial is not None:
                continue
            r = first_row[key]
            listed.append(
                {
                    "post_id": u["post_id"],
                    "unit_id": u["unit_id"],
                    "in_candidate_list": False,
                    "candidate_serial": None,
                    "candidate_name": WINNER_MARK.sub("", r["result_name"]).strip()
                    or None,
                    "result_present": True,
                    "result_serial": r["result_serial"],
                    "match_method": None,
                    "votes": votes[key],
                    "elected": True in flags[key],
                    "source_url": r["source_url"],
                    "fetched_at": r["fetched_at"],
                    "source_sha256": r["source_sha256"],
                    "source_row": r["source_row"],
                }
            )
        won = [s for s, f in flags.items() if True in f]
        if len(won) > 1:
            raise ValueError(f"Several flagged winners in {where}")
        by_serial = {c["candidate_serial"]: c for c in listed if c["in_candidate_list"]}
        if won:
            serial = pairs[won[0]][0]
            c = by_serial.get(serial, {})
            winners.append(
                {
                    "post_id": u["post_id"],
                    "unit_id": u["unit_id"],
                    "winner_basis": "result_flag",
                    "candidate_serial": serial,
                    "result_serial": first_row[won[0]]["result_serial"],
                    "winner_name": c.get("candidate_name")
                    or WINNER_MARK.sub("", result_names[won[0]]).strip(),
                    "candidate_gender": c.get("candidate_gender"),
                    "candidate_age": c.get("candidate_age"),
                    "votes": votes[won[0]],
                    "affidavit_url": c.get("affidavit_url"),
                }
            )
        elif len(by_serial) == 1 and not reported:
            c = listed[0]
            winners.append(
                {
                    "post_id": u["post_id"],
                    "unit_id": u["unit_id"],
                    "winner_basis": "sole_candidate",
                    "candidate_serial": c["candidate_serial"],
                    "result_serial": None,
                    "winner_name": c["candidate_name"],
                    "candidate_gender": c["candidate_gender"],
                    "candidate_age": c["candidate_age"],
                    "votes": None,
                    "affidavit_url": c["affidavit_url"],
                }
            )
        phase_ids = None if phases is None else [x["i"] for x in phases]
        if c_event is None or r_event is None:
            if phase_ids is not None and phase not in phase_ids:
                status = "phase_not_listed"
            else:
                raise ValueError(f"Missing saved response for {where}")
        elif reported:
            status = "results"
        elif len(by_serial) == 1:
            status = "one_candidate_no_results"
        elif by_serial:
            status = "candidates_no_results"
        else:
            status = "no_candidates"
        if not reported and status != "phase_not_listed" and phase_ids is None:
            raise ValueError(f"Seat without results lacks phase evidence: {where}")
        seats.append(
            {
                **{
                    k: u[k]
                    for k in (
                        "post_id",
                        "district_id",
                        "block_id",
                        "panchayat_id",
                        "seat_no",
                        "unit_id",
                        "district",
                        "block",
                        "panchayat",
                    )
                },
                "phases_listed": None if phase_ids is None else ";".join(phase_ids),
                "candidate_records": len(by_serial),
                "result_only_candidates": len(listed) - len(by_serial),
                "result_records": len(reported),
                "result_candidates": len(result_names),
                "winners_flagged": len(won),
                "winner_flag_partial": partial,
                "status": status,
            }
        )
        candidates.extend(listed)
        results.extend(reported)
    return seats, candidates, results, winners


def current_seat_key(post, d, b, p, s):
    if post in (1, 2):
        return (post, d, p, s)
    if post in (3, 4):
        return (post, d, p)
    if post == 5:
        return (post, d, b, s)
    return (post, d, s)


def build_current(responses, legacy_mukhiya, frame):
    lookup = {
        current_seat_key(
            u["post_id"],
            u["district_id"],
            u["block_id"],
            u["panchayat_id"],
            u["seat_no"],
        ): u["unit_id"]
        for u in frame
    }
    tables = {"winners": [], "reservations": []}
    events = [
        (key, event)
        for key, event in responses.events.items()
        if key.startswith("current/")
    ] + list(legacy_mukhiya.items())
    for key, event in sorted(events):
        kind, post = key.split("/")[1], int(key.split("/")[2][1:])
        ids = {part[0]: int(part[1:]) for part in key.rsplit("/", 1)[1].split("_")}
        body = base64.b64decode(event["body_base64"])
        sha = hashlib.sha256(body).hexdigest()
        for i, row in enumerate(decode_records(body), 1):
            t = typed(row, CURRENT_FIELDS, key)
            if t["district_id"] != ids["d"]:
                raise ValueError(f"Current feed outside district: {key}")
            if t["block_id"] != ids["b"]:
                # The zila parishad reservation feed ignores BlockID and returns the
                # whole district per block request; keep each seat once.
                if (post, kind) == (6, "reservations"):
                    continue
                raise ValueError(f"Current feed outside block: {key}")
            if "p" in ids and t["panchayat_id"] != ids["p"]:
                raise ValueError(f"Current feed outside panchayat: {key}")
            # Vacant seats are listed as placeholders: no name, age 55, a date in
            # CandidatePhotos and "ok" in Affidavit. Those values are not a person's.
            placeholder = kind == "winners" and t.get("candidate_name") is None
            if placeholder:
                t["placeholder_date"] = t.pop("photo_url")
                t["placeholder_affidavit"] = t.pop("affidavit_url")
                for column in ("candidate_age", "candidate_gender_raw"):
                    t[column] = None
            seat = current_seat_key(
                post, t["district_id"], t["block_id"], t["panchayat_id"], t["seat_no"]
            )
            record = {
                "post_id": post,
                "unit_id": lookup.get(seat),
                **({"vacant_placeholder": placeholder} if kind == "winners" else {}),
                **t,
                "source_url": event["url"],
                "fetched_at": event["fetched_at"],
                "source_sha256": sha,
                "source_row": i,
            }
            tables[kind].append(record)
    return tables


def frame_table(frame):
    return pl.DataFrame(frame)


def write_tables(out, tables):
    out.mkdir(parents=True, exist_ok=True)
    frames = {}
    # Validate every table before writing any, so a failure leaves no partial release.
    for name, model in TABLES.items():
        schema = polars_schema(model)
        rows = tables.pop(name)
        frames[name] = model.validate(
            pl.DataFrame(
                [{c: r.get(c) for c in schema} for r in rows],
                schema=schema,
                orient="row",
            ),
            lazy=True,
        )
        del rows
    files = []
    for name, model in TABLES.items():
        df = frames[name]
        path = out / f"{name}.parquet"
        temp = path.with_suffix(".tmp")
        df.write_parquet(temp, compression="zstd", statistics=True)
        temp.replace(path)
        files.append(
            {
                "path": path.name,
                "rows": df.height,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "schema": {c: str(t) for c, t in df.schema.items()},
                "unique_key": list(model.Config.unique),
            }
        )
    with (out / "dictionary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            ["table", "column", "type", "nullable", "checks", "description"],
            lineterminator="\n",
        )
        writer.writeheader()
        for name, model in TABLES.items():
            writer.writerows(dictionary_rows(name, model))
    (out / "SCHEMA.json").write_text(
        json.dumps({f["path"]: f["schema"] for f in files}, indent=2) + "\n"
    )
    (out / "CHECKSUMS").write_text(
        "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
    )
    return files


def verify(out):
    """Re-read the published files: checksums, row counts, schemas and checks."""
    manifest = json.loads((out / "MANIFEST.json").read_text())
    for info in manifest["files"]:
        path = out / info["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"Checksum differs from manifest: {path}")
        df = TABLES[path.stem].validate(pl.read_parquet(path), lazy=True)
        if df.height != info["rows"]:
            raise ValueError(f"Row count differs from manifest: {path}")
    files = {info["path"] for info in manifest["files"]}
    if files != {f"{name}.parquet" for name in TABLES}:
        raise ValueError("Release files differ from the declared tables")
    for prefix, keys in (
        ("", ["post_id", "unit_id"]),
        ("byelection_", ["phase", "post_id", "unit_id"]),
    ):
        seats = pl.read_parquet(out / f"{prefix}seats.parquet")
        names = ["candidates", "result_rows", "winners"]
        names += ["current_winners"] if not prefix else []
        for name in names:
            rows = pl.read_parquet(out / f"{prefix}{name}.parquet").drop_nulls(
                "unit_id"
            )
            orphans = rows.join(seats, on=keys, how="anti")
            if orphans.height:
                raise ValueError(
                    f"{prefix}{name} rows without a seat: {orphans.height}"
                )
    # Every by-election seat is a seat of the 2021 frame.
    unknown = pl.read_parquet(out / "byelection_seats.parquet").join(
        pl.read_parquet(out / "seats.parquet"), on=["post_id", "unit_id"], how="anti"
    )
    if unknown.height:
        raise ValueError(f"By-election seats outside the 2021 frame: {unknown.height}")
    print(json.dumps({"verified": True, "files": len(files)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--archives", type=Path, default=Path("data/interim/2021/archive")
    )
    parser.add_argument(
        "--mukhiya", type=Path, default=Path("data/raw/statewide_2021.tar.gz")
    )
    parser.add_argument(
        "--current-mukhiya", type=Path, default=Path("data/raw/portal_2021_2026")
    )
    parser.add_argument("--out", type=Path, default=Path("data/release/2021_panchayat"))
    args = parser.parse_args()
    if args.check:
        verify(args.out)
        return

    frame = (
        mukhiya_frame(args.mukhiya)
        + pq.read_table(args.archives / "offices_frame.parquet").to_pylist()
    )
    frame = [
        {
            k: u[k]
            for k in (
                "post_id",
                "district_id",
                "block_id",
                "panchayat_id",
                "seat_no",
                "unit_id",
                "district",
                "block",
                "panchayat",
            )
        }
        for u in frame
    ]
    tables = collections.defaultdict(list)
    receipts = {}
    for post in (3, 4, 5, 6, 2, 1):
        archive = (
            [args.mukhiya]
            if post == 3
            else [args.archives / f"2021_offices_p{post}.tar"]
        )
        responses = Responses(archive)
        receipts.update(responses.archives)
        units = [u for u in frame if u["post_id"] == post]
        seats, candidates, results, winners = build_post(units, responses)
        for name, rows in [
            ("seats", seats),
            ("candidates", candidates),
            ("result_rows", results),
            ("winners", winners),
        ]:
            tables[name].extend(rows)
        print(
            json.dumps(
                {
                    "post": post,
                    "seats": len(seats),
                    "candidates": len(candidates),
                    "result_rows": len(results),
                    "winners": len(winners),
                }
            ),
            flush=True,
        )
    # By-elections: seats listed per round by the portal's by-election page.
    byelections = Responses([args.archives / "byelections.tar"])
    receipts.update(byelections.archives)
    with tarfile.open(args.archives / "byelections.tar") as tar:
        member = tar.getmember("byelections/frame.parquet")
        bye_frame = pq.read_table(
            io.BytesIO(tar.extractfile(member).read())
        ).to_pylist()
    for phase in sorted({u["phase"] for u in bye_frame}):
        units = [u for u in bye_frame if u["phase"] == phase]
        built = build_post(units, byelections)
        for name, rows in zip(
            ("seats", "candidates", "result_rows", "winners"), built, strict=True
        ):
            tables[f"byelection_{name}"].extend({**r, "phase": phase} for r in rows)
        print(
            json.dumps(
                {
                    "phase": phase,
                    "seats": len(built[0]),
                    "candidates": len(built[1]),
                    "winners": len(built[3]),
                }
            ),
            flush=True,
        )
    current = Responses(
        [
            args.archives / "current_winners.tar",
            args.archives / "current_reservations.tar",
        ]
    )
    receipts.update(current.archives)
    legacy = {}
    for kind in ("winners", "reservations"):
        for path in sorted((args.current_mukhiya / kind).glob("*_p3.jsonl.gz")):
            event = completed_bytes(path.read_bytes())
            if event is None:
                raise ValueError(f"Incomplete mukhiya current-feed ledger: {path}")
            stem = path.name.removesuffix(".jsonl.gz").removesuffix("_p3")
            legacy[f"current/{kind}/p3/{stem}"] = event
    built = build_current(current, legacy, frame)
    tables["current_winners"] = built["winners"]
    tables["current_reservations"] = built["reservations"]
    files = write_tables(args.out, tables)
    manifest = {
        "year": 2021,
        "phase": PHASE,
        "offices": sorted({u["post_id"] for u in frame}),
        "excluded_source_fields": EXCLUDED,
        "files": files,
        "source_archives_sha256": receipts,
        "code_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
            if p.name
            in {"build_2021.py", "schemas_2021.py", "matching.py", "sec_portal.py"}
        },
    }
    (args.out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({f["path"]: f["rows"] for f in files}))
    verify(args.out)


if __name__ == "__main__":
    main()
