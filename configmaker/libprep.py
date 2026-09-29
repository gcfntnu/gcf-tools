"""Portable, side-effect-free library-preparation configuration selection.

Callers own source precedence. A snapshot retains the exact bytes read, so later
source edits cannot change either the selected workflow or its parameters.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


class LibprepConfigError(ValueError):
    """An actionable configuration/selection error suitable for CLI reporting."""


def _parse(content, source):
    try:
        root = yaml.compose(content, Loader=yaml.SafeLoader)
        if not isinstance(root, yaml.MappingNode) or not root.value:
            raise ValueError("expected a nonempty mapping of kit names to settings")
        names = set()
        for key, _value in root.value:
            if (
                not isinstance(key, yaml.ScalarNode)
                or key.tag != "tag:yaml.org,2002:str"
            ):
                raise ValueError("kit names must be strings")
            name = key.value.strip().casefold()
            if not name or name in names:
                raise ValueError("empty or duplicate kit name: {!r}".format(key.value))
            names.add(name)
        data = yaml.safe_load(content)
        for name, settings in data.items():
            if not isinstance(settings, dict):
                raise ValueError("entry {!r} must be a mapping".format(name))
            workflow = settings.get("workflow")
            if not isinstance(workflow, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]*", workflow
            ):
                raise ValueError("entry {!r} needs a valid workflow name".format(name))
        return data
    except (yaml.YAMLError, ValueError, UnicodeError) as error:
        raise LibprepConfigError(
            "Invalid libprep configuration {}: {}".format(source, error)
        ) from error


def validate_read_geometry(read_geometry):
    geometry = tuple(read_geometry)
    if len(geometry) not in (1, 2) or any(
        type(n) is not int or n <= 0 for n in geometry
    ):
        raise LibprepConfigError(
            "Expected one (SE) or two (PE) positive read lengths, got {!r}".format(
                geometry
            )
        )
    return geometry


@dataclass(frozen=True)
class LibprepConfig:
    source: str
    content: bytes

    def __post_init__(self):
        _parse(self.content, self.source)

    @classmethod
    def load(cls, path):
        path = Path(path)
        try:
            return cls(str(path.absolute()), path.read_bytes())
        except OSError as error:
            raise LibprepConfigError(
                "Cannot read libprep configuration {}: {}".format(path, error)
            ) from error

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()

    def select(self, kit, read_geometry):
        geometry = validate_read_geometry(read_geometry)
        layout = "SE" if len(geometry) == 1 else "PE"
        if not isinstance(kit, str) or not kit.strip():
            raise LibprepConfigError(
                "Missing Libprep/--libkit for {}".format(self.source)
            )
        name = kit.strip().casefold()
        data = _parse(self.content, self.source)
        names = {key.strip().casefold(): key for key in data}
        suffix = re.search(r" (se|pe)$", name)
        if suffix and suffix.group(1) != layout.lower():
            raise LibprepConfigError(
                "Kit {!r} conflicts with {} read geometry {}".format(
                    kit, layout, geometry
                )
            )
        candidates = [name] if suffix else [name + " " + layout.lower(), name]
        entry = next((names[key] for key in candidates if key in names), None)
        if entry is None:
            raise LibprepConfigError(
                "Unsupported library kit {!r} ({}) in {} [sha256={}]. "
                "Add the matching entry or explicitly select a configured kit using workflow: default; "
                "unknown kits never fall back to default.".format(
                    kit, layout, self.source, self.sha256
                )
            )
        settings = data[entry]
        for key, expected in (
            ("reads", layout),
            ("library_layout", "single" if layout == "SE" else "paired"),
        ):
            if key in settings and str(settings[key]).casefold() != expected.casefold():
                raise LibprepConfigError(
                    "Entry {!r} has {}={!r}, inconsistent with {}".format(
                        entry, key, settings[key], layout
                    )
                )
        return LibprepSelection(self, kit.strip(), entry, geometry)

    def write(self, path):
        """Materialize the original bytes, including comments and uncommitted edits."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.content)


@dataclass(frozen=True)
class LibprepSelection:
    config: LibprepConfig
    kit: str
    entry: str
    read_geometry: tuple

    @property
    def parameters(self):
        # Return independent data; consumers cannot mutate the captured snapshot.
        return _parse(self.config.content, self.config.source)[self.entry]

    @property
    def workflow(self):
        return self.parameters["workflow"]

    def diagnostics(self):
        return dict(
            source=self.config.source,
            sha256=self.config.sha256,
            kit=self.kit,
            entry=self.entry,
            read_geometry=list(self.read_geometry),
            workflow=self.workflow,
        )


def find_read_geometry(runfolders):
    """Read the same demultiplexer Stats.json geometry for BFQ and configmaker."""
    geometries = set()
    for directory in runfolders:
        path = Path(directory) / "Stats" / "Stats.json"
        try:
            stats = json.loads(path.read_bytes())
            lanes = stats["ReadInfosForLanes"]
            if not lanes:
                raise ValueError("ReadInfosForLanes is empty")
            for lane in lanes:
                reads = lane["ReadInfos"]
                if any(type(read["IsIndexedRead"]) is not bool for read in reads):
                    raise ValueError("IsIndexedRead must be boolean")
                geometry = validate_read_geometry(
                    [read["NumCycles"] for read in reads if not read["IsIndexedRead"]]
                )
                geometries.add(geometry)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LibprepConfigError(
                "Cannot determine read geometry from {}: {}".format(path, error)
            ) from error
    if len(geometries) != 1:
        raise LibprepConfigError(
            "Read geometry mismatch or no geometry across runfolders/lanes: {!r}".format(
                sorted(geometries)
            )
        )
    return list(geometries.pop())
