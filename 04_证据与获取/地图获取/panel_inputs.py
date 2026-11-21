"""Obtain or verify R3 map inputs without running a TSP solver."""
import argparse
import csv
import gzip
from hashlib import sha256
from pathlib import Path
import subprocess
from urllib.parse import urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
HOSTS = {"www.math.uwaterloo.ca", "comopt.ifi.uni-heidelberg.de"}
LIMIT = 2_000_000
GENERATOR_ARCHIVE_SHA = "5f041f0b9d68f2397309880919bbfde3d286e1b10b042cc07285f632cee6080a"


def checked_bytes(row, raw):
    if sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError(f'frozen map SHA256 mismatch for {row["instance"]}')
    return raw


def fetch(row):
    url = row["source_url"]
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in HOSTS:
        raise ValueError(f"unexpected source URL: {url}")
    with urlopen(url, timeout=25) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in HOSTS:
            raise ValueError(f"unexpected redirect: {response.geturl()}")
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("download exceeds the registered size limit")
    if row["recipe"] == "gzip":
        from io import BytesIO
        with gzip.GzipFile(fileobj=BytesIO(raw)) as zipped:
            raw = zipped.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("decompressed map exceeds the registered size limit")
    return raw


def generate(row, generators):
    suffix = ".exe" if (generators / (row["generator"] + ".exe")).is_file() else ""
    program = (generators / (row["generator"] + suffix)).resolve(strict=True)
    return subprocess.check_output(
        [str(program), row["dimension"], row["seed"]], timeout=25
    ).replace(b"\r\n", b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "download", "generate"))
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--id", action="append", help="limit to the specified instance IDs")
    parser.add_argument("--generators", type=Path, help="locally compiled portgen and portcgen")
    parser.add_argument("--dimacs-archive", type=Path, help="upstream codes.zip used to build generators")
    args = parser.parse_args()
    with (ROOT / "map_manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        panel = list(csv.DictReader(stream))
    known = {row["instance"] for row in panel}
    if len(panel) != 20 or len(known) != 20:
        parser.error("the frozen panel must contain 20 unique maps")
    if args.id and (unknown := set(args.id) - known):
        parser.error(f"unknown instance IDs: {', '.join(sorted(unknown))}")
    if args.mode == "generate":
        if not args.generators or not args.dimacs_archive:
            parser.error("generate requires --generators and --dimacs-archive")
        if sha256(args.dimacs_archive.read_bytes()).hexdigest() != GENERATOR_ARCHIVE_SHA:
            parser.error("upstream DIMACS codes.zip SHA256 mismatch")
    selected = [row for row in panel if not args.id or row["instance"] in args.id]
    if args.mode != "verify":
        selectable = {"direct", "gzip"} if args.mode == "download" else {"generate"}
        selected = [row for row in selected if row["recipe"] in selectable]
        if args.id and {row["instance"] for row in selected} != set(args.id):
            parser.error("requested instance needs another acquisition mode")
        args.maps.mkdir(parents=True, exist_ok=True)
    for row in selected:
        name = row["instance"]
        if name != Path(name).name:
            parser.error(f"unsafe instance name: {name}")
        target = args.maps / (name + ".tsp")
        if args.mode == "verify" or target.exists():
            checked_bytes(row, target.read_bytes())
        else:
            raw = fetch(row) if args.mode == "download" else generate(row, args.generators)
            checked_bytes(row, raw)
            with target.open("xb") as stream:
                stream.write(raw)
        print(f"{name} {row['sha256']}")
    print(f"{len(selected)} map hashes verified")


if __name__ == "__main__":
    main()
