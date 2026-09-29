from pathlib import Path

import pytest

from configmaker.configmaker import add_workflow
from configmaker.libprep import LibprepConfig, LibprepConfigError


CONTENT = b"""Kit SE:
  workflow: rnaseq
  filter:
    trim:
      fastp:
        params: '-q 17'
  db:
    reference_db: ensembl
Custom SE:
  workflow: default
"""


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "portable/workflows/gcf-workflows"
    path.mkdir(parents=True)
    (path / "libprep.config").write_bytes(CONTENT)
    return path


def test_standalone_portable_workflow_and_nested_settings(workflow):
    config = {
        "libprepkit": "Kit",
        "read_geometry": [75],
        "filter": {"subsample_fastq": 0.5},
    }
    result = add_workflow(config, src_dir=workflow.parent)
    assert result["filter"] == {
        "subsample_fastq": 0.5,
        "trim": {"fastp": {"params": "-q 17"}},
    }
    assert result["db"]["reference_db"] == "ensembl"
    assert result["workflow"] == "rnaseq"
    assert "rnaseq/rnaseq.smk" in Path("Snakefile").read_text()
    assert result["libprep_selection"]["source"] == str(workflow / "libprep.config")


def test_explicit_snapshot_wins_and_is_materialized(workflow):
    snapshot = LibprepConfig("authoritative", CONTENT.replace(b"-q 17", b"-q 19"))
    config = {"libprepkit": "Kit", "read_geometry": [75]}
    result = add_workflow(
        config,
        src_dir=workflow.parent,
        libprep_config=snapshot,
        expected_sha256=snapshot.sha256,
        expected_entry="Kit SE",
        expected_read_geometry=[75],
    )
    assert result["filter"]["trim"]["fastp"]["params"] == "-q 19"
    assert (workflow / "libprep.config").read_bytes() == snapshot.content


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"expected_sha256": "bad"}, "hash mismatch"),
        ({"expected_entry": "Kit PE"}, "entry mismatch"),
        ({"expected_read_geometry": [75, 75]}, "geometry changed"),
    ],
)
def test_inconsistent_expectations_fail_before_snakefile(workflow, kwargs, message):
    with pytest.raises(LibprepConfigError, match=message):
        add_workflow(
            {"libprepkit": "Kit", "read_geometry": [75]},
            src_dir=workflow.parent,
            **kwargs,
        )
    assert not Path("Snakefile").exists()


def test_unknown_kit_does_not_fall_back(workflow):
    with pytest.raises(LibprepConfigError, match="Unsupported library kit"):
        add_workflow(
            {"libprepkit": "Kti", "read_geometry": [75]}, src_dir=workflow.parent
        )
    result = add_workflow(
        {"libprepkit": "Custom", "read_geometry": [75]}, src_dir=workflow.parent
    )
    assert result["workflow"] == "default"
