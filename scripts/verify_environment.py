"""Reject incomplete or drifted exact development baselines, including overrides."""
import importlib.metadata
from pathlib import Path
import re
import sys


def verify(path):
    expected_names = set()
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise RuntimeError("Development baselines require one exact name==version per line: " + line)
        name, expected = match.groups()
        canonical = normalize(name)
        if canonical in expected_names:
            raise RuntimeError("Duplicate baseline requirement: " + name)
        expected_names.add(canonical)
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError("Dependency drift: " + name + " expected " + expected + ", found " + actual)
    installed = {}
    for distribution in importlib.metadata.distributions():
        name = normalize(distribution.metadata["Name"])
        if name in installed:
            raise RuntimeError("Duplicate installed distribution: " + name)
        installed[name] = distribution.version
    unexpected = set(installed) - expected_names - {"gcf-tools"}
    if unexpected:
        raise RuntimeError("Unpinned development dependencies: " + ", ".join(sorted(unexpected)))
    print("Exact complete development dependency baseline verified")


if __name__ == "__main__":
    verify(sys.argv[1])
