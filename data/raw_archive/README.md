# Bihar raw-data archive

Raw source material too large for git. The files live here, git-ignored; this README and `MANIFEST.csv` (path, SHA-256, bytes, origin) are tracked.

**Download:** Google Drive: _link to be added_ — `local_elections_bihar_raw_<date>.tar.gz`, with its `.sha256` alongside.

To restore: extract the tarball into `data/raw_archive/`, then run `make raw-verify`. To publish a new archive: `make raw-archive` (it verifies first) and upload `dist/raw_archive/*`.

| Folder | Files | What it is |
|---|---:|---|
| `central_handoff/PRI_WINNER_2011/` | 290 | 2011 panchayat winner lists |
| `central_handoff/GPS_GKP_PSS_ZPS/` | 32 | Gram Panchayat, Gram Kachahari, Panchayat Samiti and Zila Parishad lists, by division |
| `central_handoff/Mukhiya_2006/` | 38 | 2006 Mukhiya lists by district |
| `central_handoff/Sarpanch/` | 35 | Sarpanch (village court head) lists by district |

`central_handoff/` came unaltered from `data/bihar` of [in-rolls/local_elections](https://github.com/in-rolls/local_elections) at commit `fa4c4e79`. None of it is parsed yet; the released tables cover 2016 and 2021.
