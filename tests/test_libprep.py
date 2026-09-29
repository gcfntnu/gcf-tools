import hashlib
import json

import pytest

from configmaker.libprep import LibprepConfig, LibprepConfigError, find_read_geometry


CONFIG = b"""# local edits must survive
Example SE:
  workflow: rnaseq
  library_layout: single
  filter:
    trim:
      fastp:
        params: '-q 17'
Example PE:
  workflow: metagenome
  library_layout: paired
Custom PE:
  workflow: default
"""


@pytest.fixture
def snapshot(tmp_path):
    source = tmp_path / "libprep.config"
    source.write_bytes(CONFIG)
    return LibprepConfig.load(source)


@pytest.mark.parametrize(
    "kit,geometry,entry,workflow",
    [
        ("example", [75], "Example SE", "rnaseq"),
        (" EXAMPLE pe ", [150, 150], "Example PE", "metagenome"),
        ("Custom", [150, 150], "Custom PE", "default"),
    ],
)
def test_geometry_selects_entry(snapshot, kit, geometry, entry, workflow):
    selected = snapshot.select(kit, geometry)
    assert selected.entry == entry
    assert selected.workflow == workflow
    assert selected.config.sha256 == hashlib.sha256(CONFIG).hexdigest()


@pytest.mark.parametrize(
    "kit,geometry,message",
    [
        ("Misspelled", [75], "Unsupported library kit"),
        ("Example PE", [75], "conflicts with SE"),
        (None, [75], "Missing Libprep"),
        ("Example", [], "positive read lengths"),
        ("Example", [0], "positive read lengths"),
    ],
)
def test_selection_errors(snapshot, kit, geometry, message):
    with pytest.raises(LibprepConfigError, match=message):
        snapshot.select(kit, geometry)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"[]",
        b"x: [",
        b"x: null",
        b"x: {}",
        b"x: {workflow: ../bad}",
        b"x: {workflow: good}\nX: {workflow: other}",
        b"x: {workflow: good}\nx: {workflow: other}",
    ],
)
def test_malformed_configuration(tmp_path, content):
    source = tmp_path / "bad.config"
    source.write_bytes(content)
    with pytest.raises(LibprepConfigError, match="Invalid libprep configuration"):
        LibprepConfig.load(source)


def test_missing_configuration(tmp_path):
    with pytest.raises(LibprepConfigError, match="Cannot read libprep configuration"):
        LibprepConfig.load(tmp_path / "missing")


def test_source_edits_and_consumer_mutation_do_not_change_snapshot(snapshot, tmp_path):
    from pathlib import Path

    Path(snapshot.source).write_text("broken: [")
    selected = snapshot.select("Example", [75])
    selected.parameters["filter"]["trim"]["fastp"]["params"] = "changed"
    assert selected.parameters["filter"]["trim"]["fastp"]["params"] == "-q 17"
    destination = tmp_path / "project/src/gcf-workflows/libprep.config"
    snapshot.write(destination)
    assert destination.read_bytes() == CONFIG


def test_conflicting_layout(tmp_path):
    snapshot = LibprepConfig(
        "memory", b"Kit PE: {workflow: default, library_layout: single}"
    )
    with pytest.raises(LibprepConfigError, match="inconsistent with PE"):
        snapshot.select("Kit", [150, 150])


def test_geometry_all_lanes_and_runfolders(tmp_path):
    def stats(path, lengths):
        path.mkdir()
        (path / "Stats").mkdir()
        reads = [{"IsIndexedRead": False, "NumCycles": n} for n in lengths]
        reads.insert(1, {"IsIndexedRead": True, "NumCycles": 8})
        (path / "Stats/Stats.json").write_text(
            json.dumps(
                {"ReadInfosForLanes": [{"ReadInfos": reads}, {"ReadInfos": reads}]}
            )
        )
        return path

    a = stats(tmp_path / "a", [150, 150])
    b = stats(tmp_path / "b", [150, 150])
    assert find_read_geometry([a, b]) == [150, 150]
    c = stats(tmp_path / "c", [75])
    with pytest.raises(LibprepConfigError, match="mismatch"):
        find_read_geometry([a, c])
    with pytest.raises(LibprepConfigError, match="Stats.json"):
        find_read_geometry([tmp_path / "missing"])
