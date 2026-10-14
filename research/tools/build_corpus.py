"""Builds tests/conformance/cases.json from the recorded probe suites and their results.

Only `check` probes are kept: they are the ones that `/import ... dry-run` judged without running anything.
Usage: python research/tools/build_corpus.py
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITES = [
    ("suite1_lexical", "suite1_lexical.txt"),
    ("suite2_vars", "suite2_vars.txt"),
    ("suite3_values", "suite3.txt"),
    ("suite4_commands", "suite4.txt"),
    ("suite5_misc", "suite5.txt"),
    ("suite6_state", "suite6.txt"),
    ("suite7_layout", "suite7.txt"),
    ("suite8_adjacency", "suite8.txt"),
    ("suite9_wordchars", "suite9.txt"),
    ("suite10_expr", "suite10.txt"),
    ("suite11_closers", "suite11.txt"),
    ("suite12_misc", "suite12.txt"),
    ("suite13_scope", "suite13.txt"),
    ("suite14_declare", "suite14.txt"),
    ("suite16_pathstate", "suite16.txt"),
    ("suite17_pathleak", "suite17.txt"),
    ("suite18_barewords", "suite18.txt"),
]
LINE = re.compile(r"^(?P<id>\S+)\s+(?P<mode>check)\s+.*\s-> (?P<verdict>(?:OK|ERR: |\?\? ).*)$")
ERR = re.compile(r"^ERR: (?P<msg>.*?) \(line (?P<line>\d+) column (?P<col>\d+)\)")


def load(name):
    path = ROOT / "research" / "suites" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_results(path):
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        verdict = m["verdict"].split("   #")[0]
        verdict = re.sub(r"\s*\[Script Error: found \d+ error\(s\) in import file\]\s*$", "", verdict).strip()
        out[m["id"]] = verdict
    return out


def main():
    cases = []
    skipped = []
    for module, results in SUITES:
        probes = load(module).PROBES
        verdicts = parse_results(ROOT / "research" / "results" / results)
        section = ""
        for item in probes:
            if isinstance(item, str):
                section = item.split(" (")[0].strip().lower()
                continue
            pid, mode, source, note = item[0], item[1], item[2], item[3]
            if mode != "check":
                continue
            verdict = verdicts.get(pid)
            if verdict is None:
                skipped.append(pid)
                continue
            case = {"id": pid, "section": section, "note": note, "source": source}
            if verdict == "OK":
                case["valid"] = True
            else:
                m = ERR.match(verdict)
                case["valid"] = False
                if m:
                    case["message"] = m["msg"]
                    case["line"] = int(m["line"])
                    case["column"] = int(m["col"])
                else:
                    case["message"] = re.sub(r"^ERR: ", "", verdict)
            cases.append(case)
    dest = ROOT / "tests" / "conformance" / "cases.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cases, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(cases)} cases to {dest.relative_to(ROOT)}; no recorded verdict for: {skipped}")


if __name__ == "__main__":
    sys.exit(main())
