# Historical handoff (2011 reports, 2006 workbooks)

The source files Bihar's panchayat data started from, as first committed to
in-rolls/local_elections (commit `e7b5224d`, 2022-10-28) and kept there until
the state moved to this repository (last at `fa4c4e79`). They arrived as a
handoff; who downloaded them, from where and when was not recorded. The layout
(one folder per district, one PDF per office) looks like the State Election
Commission's own exports.

Files are byte-identical to `local_elections@fa4c4e79:data/bihar/`
(`MANIFEST.json` gives each file's sha256 and git blob id, checked against that
commit). Left out: the old readme and 11 Windows `Desktop.ini` files.

| Folder | What | Files |
|---|---|---:|
| `PRI_WINNER_2011/<DISTRICT>/` | 2011 winner reports, 23 districts, one PDF per office: GPM Mukhiya, GPS ward member, GKP / GKS gram kachahari, PSS samiti member, ZPS zila parishad member; some `WPOST2001-2006` | 290 incl. below |
| `PRI_WINNER_2011/Winner-Runner Reports/` | winner and runner-up reports for 8 districts | |
| `Mukhiya_2006/` | Mukhiya workbooks, one per district: winner profiles (name, age, education, income, children, caste category); no seat reservation and no printed year | 38 |
| `Sarpanch/` | Sarpanch workbooks | 35 |
| `GPS_GKP_PSS_ZPS/<DIVISION>/` | district workbooks for ward, kachahari, samiti and zila parishad members, headed 2006 | 32 |

Only the 23 Mukhiya PDFs, the Gaya workbook and the Gaya runner-up PDF are
parsed (`data/2011/mukhiya_reports`, `data/2011/gaya_mukhiya`); their working
copies are in the Zenodo 2011 source archive. Everything else here is unparsed.
