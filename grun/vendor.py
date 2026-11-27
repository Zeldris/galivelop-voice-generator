"""`grun vendor`: copy this package into a consumer with a manifest and a sha256 fingerprint, and verify such a copy.

A Python consumer (gimg, gvoice) vendors ``grun`` (DDD section 0): a copy that records its version and the fingerprint
of its files, plus a test that compares that fingerprint with the one pinned in the consumer. `export` writes the copy
and its ``VENDOR.json``; `verify` reads a copy back and says what differs (public API: the consumer's test calls it).
The fingerprint covers the package's ``*.py`` and ``locales/*.json`` files, never ``__pycache__`` or the manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .errors import GrunError

SCHEMA = "grun.vendor/0"
MANIFEST = "VENDOR.json"
PACKAGE = Path(__file__).resolve().parent


class VendorError(GrunError):
    """A vendoring step failed; the code is ``vendor.<what>``."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root: Path) -> dict[str, str]:
    """``{relative posix path: sha256}`` of the files that make up a copy of the package at `root` (regular files only)."""
    found = {}
    for pattern in ("*.py", "locales/*.json"):
        for path in sorted(Path(root).glob(pattern)):
            if path.is_file() and not path.is_symlink():
                found[path.relative_to(root).as_posix()] = _sha256(path)
    return found


def fingerprint(files: dict[str, str]) -> str:
    """One sha256 over the sorted ``path NUL sha256 LF`` lines of `files` (as `collect` returns them)."""
    text = "".join("%s\0%s\n" % (name, files[name]) for name in sorted(files))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source() -> str | None:
    """``<short sha>`` of the repository this package lives in, ``-dirty`` with changes under it; None outside git."""
    def git(*args):
        return subprocess.run(["git", "-C", str(PACKAGE), *args], capture_output=True, text=True, timeout=30)
    try:
        head = git("rev-parse", "--short=12", "HEAD")
        if head.returncode != 0:
            return None
        dirty = git("status", "--porcelain", "--", ".").stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return head.stdout.strip() + ("-dirty" if dirty else "")


def export(dest: Path, *, source: str | None = None) -> dict:
    """Copy the package to ``<dest>/grun`` and write its manifest; returns the manifest.

    An existing ``<dest>/grun`` is replaced only when it is itself a vendored copy (it holds a manifest); anything else
    raises ``vendor.not_vendored`` and nothing is touched."""
    target = Path(dest) / "grun"
    if target.exists():
        if not (target / MANIFEST).is_file():
            raise VendorError("vendor.not_vendored", path=str(target))
        shutil.rmtree(target)
    (target / "locales").mkdir(parents=True)
    files = collect(PACKAGE)
    for name in files:
        shutil.copyfile(PACKAGE / name, target / name)
    manifest = {"schema": SCHEMA, "version": __version__, "source": source if source is not None else _source(),
                "fingerprint": fingerprint(files), "files": files}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(root: Path, *, pinned: str | None = None) -> list[dict]:
    """Problems of the vendored copy at `root` (the ``grun`` folder), ``[]`` when it is intact.

    Each is ``{"code", "params"}``: ``vendor.no_manifest`` / ``vendor.bad_manifest`` (nothing else is checked),
    ``vendor.missing``, ``vendor.changed``, ``vendor.extra`` (per file, against the manifest), ``vendor.fingerprint``
    (the manifest's own fingerprint does not match its file list) and, with `pinned`, ``vendor.pinned`` (the copy's
    fingerprint is not the one the consumer pinned)."""
    root = Path(root)
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [{"code": "vendor.no_manifest", "params": {"path": str(root)}}]
    except (OSError, ValueError):
        return [{"code": "vendor.bad_manifest", "params": {"path": str(root)}}]
    listed = manifest.get("files") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or not isinstance(listed, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in listed.items())):
        return [{"code": "vendor.bad_manifest", "params": {"path": str(root)}}]
    actual = collect(root)
    problems = []
    for name in sorted(set(listed) | set(actual)):
        if name not in actual:
            problems.append({"code": "vendor.missing", "params": {"file": name}})
        elif name not in listed:
            problems.append({"code": "vendor.extra", "params": {"file": name}})
        elif actual[name] != listed[name]:
            problems.append({"code": "vendor.changed", "params": {"file": name}})
    if manifest.get("fingerprint") != fingerprint(listed):
        problems.append({"code": "vendor.fingerprint", "params": {"expected": fingerprint(listed),
                                                                  "found": str(manifest.get("fingerprint"))}})
    if pinned is not None and pinned != fingerprint(actual):
        problems.append({"code": "vendor.pinned", "params": {"expected": pinned, "found": fingerprint(actual)}})
    return problems


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        raise SystemExit(2)


def main(argv=None) -> int:
    """``python -m grun vendor (--dest DIR | --verify DIR [--pinned SHA256]) [--json]``: exit 0 on success, 1 on
    problems or a refusal, 2 on bad usage."""
    parser = _Parser(prog="grun vendor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dest", help="folder that will hold the copy (as <dest>/grun)")
    group.add_argument("--verify", metavar="DIR", help="the vendored grun folder to verify")
    parser.add_argument("--pinned", help="with --verify: the fingerprint the consumer pinned")
    parser.add_argument("--json", action="store_true", help="print the manifest or the problems as JSON")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    return run(args)


def run(args) -> int:
    """Run ``vendor``: exit 0 on success, 1 on problems or a refusal, 2 on bad usage."""
    if args.pinned and not args.verify:
        print("grun vendor: --pinned needs --verify", file=sys.stderr)
        return 2
    if args.dest:
        try:
            manifest = export(Path(args.dest))
        except GrunError as exc:
            print(exc.message(), file=sys.stderr)
            return 1
        print(json.dumps(manifest, indent=2, sort_keys=True) if args.json
              else "grun %s vendored to %s/grun (fingerprint %s)" % (manifest["version"], args.dest,
                                                                    manifest["fingerprint"]))
        return 0
    problems = verify(Path(args.verify), pinned=args.pinned)
    if args.json:
        print(json.dumps(problems, indent=2, sort_keys=True))
    else:
        for p in problems:
            print("%s %s" % (p["code"], json.dumps(p["params"], sort_keys=True, ensure_ascii=False)))
        if not problems:
            print("ok")
    return 1 if problems else 0
