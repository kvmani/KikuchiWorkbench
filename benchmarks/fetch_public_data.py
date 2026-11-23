"""Download public benchmark data (not committed to Git) and verify checksums.

    python benchmarks/fetch_public_data.py --dest ~/kwb_data al_si ni_master

Datasets (CC-BY-4.0; cite the Zenodo records in any report):
  al_si      Zenodo 20290635  al10si_oxford.zip  (Oxford .ebsp Al-Si scan + EMsoft Al/Si masters)
  ni_master  Zenodo 7498645   ni_mc_mp_20kv.h5   (EMsoft dynamical Ni master, reference projection checks)
  al_master  Zenodo 7628365   al_mc_mp_20kv.h5   (EMsoft dynamical Al master)
  si_master  Zenodo 7498729   si_mc_mp_20kv.h5   (EMsoft dynamical Si master)
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

DATASETS = {
    "al_si": ("20290635", "al10si_oxford.zip"),
    "ni_master": ("7498645", "ni_mc_mp_20kv.h5"),
    "al_master": ("7628365", "al_mc_mp_20kv.h5"),
    "si_master": ("7498729", "si_mc_mp_20kv.h5"),
}


def record_files(record: str) -> dict:
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{record}") as r:
        d = json.load(r)
    return {f["key"]: f for f in d["files"]}


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def fetch(name: str, dest: Path) -> Path:
    record, key = DATASETS[name]
    meta = record_files(record)[key]
    out = dest / name / key
    out.parent.mkdir(parents=True, exist_ok=True)
    expected = meta["checksum"].split(":", 1)[1]
    if out.exists() and md5(out) == expected:
        print(f"{name}: present and verified ({out})")
        return out
    url = meta["links"]["self"]
    tmp = out.with_suffix(out.suffix + ".part")
    print(f"{name}: downloading {meta['size'] / 1e6:.0f} MB from Zenodo {record} ...", flush=True)
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 22)
            if not b:
                break
            f.write(b)
    got = md5(tmp)
    if got != expected:
        tmp.unlink()
        sys.exit(f"{name}: checksum mismatch (got {got}, expected {expected})")
    tmp.rename(out)
    (out.parent / "SOURCE.json").write_text(json.dumps(
        {"zenodo_record": record, "file": key, "md5": expected, "license": "CC-BY-4.0"}, indent=2))
    print(f"{name}: verified md5 {expected} -> {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+", choices=sorted(DATASETS))
    ap.add_argument("--dest", default=str(Path.home() / "kwb_data"))
    a = ap.parse_args()
    for n in a.names:
        fetch(n, Path(a.dest).expanduser())
