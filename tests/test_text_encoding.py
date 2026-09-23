"""Explicit text encoding contract (v34.60).

Without an encoding, open() and Path.read_text() use the locale encoding:
UTF-8 on Linux, cp1252 on a German or English Windows. A source file with a
non-ASCII character then fails to read on Windows only (it broke
tests/test_factor_injection_guard.py). Every text-mode open() and
read_text() in the project folders names its encoding.
"""
import ast

from tests._paths import REPO

FOLDERS = ("engine", "db", "ui", "pages", "tools", "tests")


def _literal(node):
    return node.value if isinstance(node, ast.Constant) else None


def _missing_encoding(call):
    """True for a text-mode open()/read_text() call without an encoding."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        mode_pos, enc_pos = 1, 3                     # open(file, mode, buffering, encoding)
    elif isinstance(func, ast.Attribute) and func.attr == "open":
        mode_pos, enc_pos = 0, 2                     # Path.open(mode, buffering, encoding)
    elif isinstance(func, ast.Attribute) and func.attr == "read_text":
        mode_pos, enc_pos = None, 0                  # Path.read_text(encoding, errors)
    else:
        return False
    kw = {k.arg: k.value for k in call.keywords}
    if "encoding" in kw or len(call.args) > enc_pos:
        return False
    mode = kw.get("mode")
    if mode is None and mode_pos is not None and len(call.args) > mode_pos:
        mode = call.args[mode_pos]
    mode_text = _literal(mode) if mode is not None else "r"
    return not (isinstance(mode_text, str) and "b" in mode_text)


def offenders(root=REPO):
    out = []
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _missing_encoding(node):
                    out.append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    return out


def test_every_text_open_names_its_encoding():
    assert offenders() == []


def test_the_scan_recognises_each_form():
    def check(src):
        return _missing_encoding(ast.parse(src).body[0].value)

    assert check("open(p)")
    assert check("open(p, 'r')")
    assert check("open(p, mode='w')")
    assert check("p.open()")
    assert check("p.read_text()")
    assert not check("open(p, encoding='utf-8')")
    assert not check("open(p, 'rb')")
    assert not check("p.open('rb')")
    assert not check("p.read_text('utf-8')")
    assert not check("p.read_text(encoding='utf-8')")
    assert not check("len(p)")
