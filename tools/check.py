"""One quality gate for every change (v34.59): the checks the ship ceremony and CI run.

Usage:
    python tools/check.py                 # lint, types, name scan, wording scan
    python tools/check.py --tests         # the same plus the full pytest suite
    python tools/check.py --base main     # wording scan of the lines added since `main`

Checks:
1. ruff: undefined names (F821); syntax, redefinition and comparison errors
   (E9, F63, F7, F82, F811); unused imports (F401).
2. mypy over the scope set in pyproject.toml.
3. Customer-name scan over every file that ships or is tracked by git. The
   names are stored only as salted SHA-256 digests, so this file never
   contains them; a match reports the text found in the scanned file.
4. Wording scan over the lines added since the base: no em dash, none of the
   banned filler words.
5. With --tests: the full suite (includes the synthetic golden gate).

Exit code 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.package_release import release_file_list  # noqa: E402

_SALT = "kromi-name-scan:"

#: Customer names, lower-cased and accent-folded: single words and two-word
#: names (matched on adjacent words).
BANNED_FOLDED_DIGESTS: frozenset[str] = frozenset({
    "a2e56cb1f331709deca8082947f8f748a47bfe7cb47e2ba1f3e44a1529ff6f9d",
    "6ff6b34d3fd360964ba9e368f3584d71d344a24e4ed56307e10e324429f0f311",
    "41282b9afa741ef6d7764f9960879c82577bcd202feb23063090d3f69a16ee36",
    "322742b2ee2253dadbc0c89a813601296714333d3db8bd93e0dce5084ae8c4f2",
    "b1b1da59afabe7e3c1025ec5aca2176af1fff63efdcff056f0ecaf1136797e02",
    "97321b41c3d0f762afdb44d3c2bec8fbb15a934e06e0d6cfef421f5e6bf9a14e",
    "b6a9847c261dd2d1cceb40df2b8fd12698efbb4f9da097d0d00927f380eab58c",
    "6ecc4a92b84eb0cd08f89b3fcf398d9553d22db63bbe67aa3cbb3689455a518f",
    "8796881dbec3f02e9e797c0acb4a878c5053d0baa6240700327010474c9d1a57",
    "c3bccee96f6c654888d0941a2cb072a02b8eeb68ee2c007461437d8a4853db40",
    "0942ffab20b36e39c1fc6a51565e722509e689bf8ff67b4d41d9a8e4b2659eda",
    "feb5006b6edd4ca71bcce76621bbec234bc6d1f199acb5d977755095eec50e83",
    "b3c2938326144319d8e414c38e48bb6961e895d0e48e807fc1d16b2ef69b5c1a",
    "e7f94e520905633620215a6058494a43bccb7ebde14eee709aac2c9b7240dace",
    "5ec239da2de8951a14c50168c17cc3c436b5216820f63a16f9b99b5efd4c1264",
    "d0c4ad76f78a540aa5fc42914621e753533978f4e1d0e300dcb74c03adad1165",
    "55288907bd17d1682460f33a5638be198d948b2a24e90749a240712f75a0efb2",
    "0a020c53c209ba01ead010215268192361d75205adcfc4276a5506841e732fb7",
    "f9200f0189091cc8c8a8455b5440d98e51936916e4082c195da402861535c30b",
    "85fa9a7a374f0ceb4c5efde9ea6697d3aa1543622d685fa6370c91ab9ffc186a",
    "0acac96ae725bea3425970efaea0d09aba7f3105c497bb27d3bcda0273623998",
})

#: Names that are ordinary words in lower case and only a name in capitals.
BANNED_EXACT_DIGESTS: frozenset[str] = frozenset({
    "d2ac5074f36fa05024f4b8a54a6ea014206e0fe059e8f682e971584d6f06d176",
})

#: Filler words the project does not use, plus the em dash.
BANNED_WORDING = re.compile(
    r"leverage|seamless|delve|simply,|obviously|honestly|genuinely|actually|—",
    re.IGNORECASE,
)

_WORD = re.compile(r"[^\W_]+")  # letters (any script) and digits
_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".db", ".pyc"}
_ZIP_SUFFIXES = {".xlsx", ".xlsm", ".docx", ".pptx"}


def name_digest(text: str, *, exact: bool = False) -> str:
    """The digest a name is stored under (``exact`` for case-sensitive names)."""
    key = ("exact:" + text) if exact else text
    return hashlib.sha256((_SALT + key).encode("utf-8")).hexdigest()


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def find_banned_names(
    text: str,
    *,
    folded: Iterable[str] = BANNED_FOLDED_DIGESTS,
    exact: Iterable[str] = BANNED_EXACT_DIGESTS,
) -> list[str]:
    """Every word or adjacent word pair of ``text`` whose digest is banned.

    Returns the matching text as it appears in ``text`` (sorted, unique).
    """
    folded_set, exact_set = set(folded), set(exact)
    words = _WORD.findall(text)
    found: set[str] = set()
    for i, word in enumerate(words):
        if name_digest(_fold(word)) in folded_set or name_digest(word, exact=True) in exact_set:
            found.add(word)
        if i + 1 < len(words):
            pair = f"{words[i]} {words[i + 1]}"
            if name_digest(_fold(pair)) in folded_set:
                found.add(pair)
    return sorted(found)


def _text_of(path: Path) -> str:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in _ZIP_SUFFIXES:
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                return "\n".join(z.read(n).decode("utf-8", "ignore")
                                 for n in z.namelist() if n.endswith(".xml"))
        except zipfile.BadZipFile:
            return data.decode("utf-8", "ignore")
    if suffix in _BINARY_SUFFIXES:
        return ""
    return data.decode("utf-8", "ignore")


def project_files(root: Path = ROOT) -> list[str]:
    """Files git tracks (plus new, not-ignored ones), else the release list."""
    if (root / ".git").exists():
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, check=True).stdout
        return sorted({p for p in out.splitlines() if p and (root / p).is_file()})
    return release_file_list(root)


def scan_names(root: Path = ROOT, files: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Customer names found per file (empty dict when the tree is clean)."""
    hits: dict[str, list[str]] = {}
    for rel in (project_files(root) if files is None else files):
        found = find_banned_names(_text_of(root / rel))
        if found:
            hits[rel] = found
    return hits


def added_lines(base: str, root: Path = ROOT) -> Iterator[tuple[str, str]]:
    """(file, line) for every line added since ``base``, including uncommitted work."""
    diff = subprocess.run(["git", "diff", "--unified=0", "--no-color", base, "--"],
                          cwd=root, capture_output=True, text=True, check=True).stdout
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            yield current, line[1:]
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                               cwd=root, capture_output=True, text=True, check=True).stdout
    for rel in untracked.splitlines():
        path = root / rel
        if path.is_file() and path.suffix.lower() not in _BINARY_SUFFIXES | _ZIP_SUFFIXES:
            for text in path.read_text("utf-8", "ignore").splitlines():
                yield rel, text


def scan_wording(lines: Iterable[tuple[str, str]]) -> list[str]:
    """``file: line`` for every added line with banned wording."""
    return [f"{f}: {t.strip()[:120]}" for f, t in lines if BANNED_WORDING.search(t)]


def _run(label: str, cmd: list[str]) -> bool:
    print(f"== {label}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tests", action="store_true", help="also run the full pytest suite")
    parser.add_argument("--base", default=None,
                        help="git ref for the wording scan (default: origin/main, else main)")
    args = parser.parse_args(argv)

    failures: list[str] = []
    py = sys.executable
    for label, cmd in (
        ("undefined names", [py, "-m", "ruff", "check", "--select", "F821", "."]),
        ("lint", [py, "-m", "ruff", "check", "--select", "E9,F63,F7,F82,F811", "."]),
        ("unused imports", [py, "-m", "ruff", "check", "--select", "F401", "."]),
        ("types", [py, "-m", "mypy"]),
    ):
        if not _run(label, cmd):
            failures.append(label)

    print("== customer names", flush=True)
    names = scan_names()
    for rel, found in names.items():
        print(f"   {rel}: {', '.join(found)}")
    if names:
        failures.append("customer names")

    if (ROOT / ".git").exists():
        base = args.base
        if base is None:
            probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main"],
                                   cwd=ROOT, capture_output=True)
            base = "origin/main" if probe.returncode == 0 else "main"
        print(f"== wording (lines added since {base})", flush=True)
        try:
            wording = scan_wording(added_lines(base))
        except subprocess.CalledProcessError as exc:
            wording = [f"git diff against {base} failed: {exc}"]
        for item in wording:
            print(f"   {item}")
        if wording:
            failures.append("wording")
    else:
        print("== wording: skipped (not a git checkout)")

    if args.tests and not _run("tests", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]):
        failures.append("tests")

    print("FAILED: " + ", ".join(failures) if failures else "All checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
