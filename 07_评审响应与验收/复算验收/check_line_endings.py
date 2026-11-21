"""Verify byte preservation on disposable checkouts of the reference package."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "core.longpaths=true", "-C", str(root), *args],
        stderr=subprocess.PIPE,
    )


def checkout(source, target, commit, *, autocrlf):
    target.mkdir()
    # Copy the object database and refs from the exact local commit into an empty
    # fixture. Do not copy the source index or worktree.
    shutil.copytree(source / ".git", target / ".git", ignore=shutil.ignore_patterns("index"))
    git(target, "update-ref", "--no-deref", "HEAD", commit)
    git(
        target, "-c", f"core.autocrlf={str(autocrlf).lower()}",
        "-c", "core.safecrlf=false", "read-tree", "--reset", "-u", commit,
    )


def manifest_entries(raw):
    entries = {}
    for line in raw.decode("utf-8-sig").splitlines():
        digest, path = line.split("  ", 1)
        parsed = PurePosixPath(path)
        if len(digest) != 64 or not path or parsed.is_absolute() or ".." in parsed.parts or path in entries:
            raise ValueError(f"Invalid manifest entry: {line!r}")
        entries[path] = digest.lower()
    return entries


def audit(source, commit, checkout, manifest):
    report = {"verified": 0, "lf_to_crlf_only": [], "other_mismatch": []}
    for name, expected in manifest.items():
        observed = (checkout / name).read_bytes()
        if hashlib.sha256(observed).hexdigest() == expected:
            report["verified"] += 1
            continue
        original = git(source, "show", f"{commit}:{name}")
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError(f"Committed baseline does not match its manifest: {name}")
        destination = "lf_to_crlf_only" if observed == original.replace(b"\n", b"\r\n") else "other_mismatch"
        report[destination].append(name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--commit", default="HEAD")
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out.resolve()
    out.mkdir()
    base = git(source, "rev-parse", f"{args.commit}^{{commit}}").decode().strip()
    manifest = manifest_entries(git(source, "show", f"{base}:SHA256SUMS.txt"))

    checkout(source, out / "old", base, autocrlf=True)
    before = audit(source, base, out / "old", manifest)

    patched = out / "patch"
    checkout(source, patched, base, autocrlf=False)
    shutil.copyfile(Path(__file__).with_name(".gitattributes"), patched / ".gitattributes")
    git(patched, "-c", "core.autocrlf=false", "add", "--", ".gitattributes")
    git(
        patched, "-c", "user.name=Local regression", "-c", "user.email=regression@example.invalid",
        "commit", "-m", "Preserve package artifact bytes",
    )
    proposed = git(patched, "rev-parse", "HEAD").decode().strip()
    diff = git(patched, "diff", "--name-status", base, proposed).decode().strip()
    if diff != "A\t.gitattributes":
        raise RuntimeError(f"The local regression changed additional files: {diff!r}")

    checkout(patched, out / "new", proposed, autocrlf=True)
    after = audit(source, base, out / "new", manifest)
    attributes = git(out / "new", "check-attr", "text", "--", "SHA256SUMS.txt").decode().strip()

    if before["other_mismatch"] or after["lf_to_crlf_only"] or after["other_mismatch"] or not before["lf_to_crlf_only"]:
        raise RuntimeError(f"Unexpected checkout results: {before!r} {after!r}")
    report = {
        "source_commit": base, "test_commit_local_only": proposed,
        "git": git(source, "--version").decode().strip(),
        "manifest_entries": len(manifest), "configuration": "core.autocrlf=true in both fresh checkouts",
        "baseline": before, "with_gitattributes": after,
        "attributes_test": attributes, "tracked_change_in_test": diff,
    }
    (out.parent / "line_ending_regression.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"{len(before['lf_to_crlf_only'])}/{len(manifest)} LF-to-CRLF mismatches before; "
          f"{after['verified']}/{len(manifest)} files match after.")


if __name__ == "__main__":
    main()
