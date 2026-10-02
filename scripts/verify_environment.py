"""Reject incomplete or drifted exact development baselines, including overrides."""
import importlib.metadata
from pathlib import Path
import re
import sys


def verify(path):
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise RuntimeError("Development baselines require one exact name==version per line: " + line)
        name, expected = match.groups()
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError("Dependency drift: " + name + " expected " + expected + ", found " + actual)
    print("Exact development dependency baseline verified")


if __name__ == "__main__":
    verify(sys.argv[1])
