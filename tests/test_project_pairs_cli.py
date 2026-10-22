"""Installed configmaker selects isolated project metadata and workflow inputs."""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from test_project_pairs import A, B, pair, run_info
from test_validation import customer_row, submission_form


@pytest.fixture
def flowcell(tmp_path):
    run = tmp_path / "990101_SYNTHETIC_0001_ASYNTHETIC"
    run.mkdir()
    sa, fa = pair(run, A, "ALPHA", "AAAAAAAA", options="[CustomOptions]\nLibprep,Alpha\nOrganism,Human\nSyntheticOption,alpha\n",
                  settings="[Settings]\nOverrideCycles,Y75;I8;I8;N150\n")
    sb, fb = pair(run, B, "BETA", "CCCCCCCC", options="[CustomOptions]\nLibprep,Beta\nOrganism,Mouse\nSyntheticOption,beta\n")
    run_info(run / "RunInfo.xml")
    (run / "Stats").mkdir()
    (run / "Stats/Stats.json").write_text(json.dumps({"ReadInfosForLanes": [{"ReadInfos": [
        {"IsIndexedRead": False, "NumCycles": 75}, {"IsIndexedRead": False, "NumCycles": 150}]}]}))
    for project, sample, lengths in ((A, "ALPHA", [75]), (B, "BETA", [75, 150])):
        (run / project).mkdir()
        manifest = []
        for mate, length in enumerate(lengths, 1):
            filename = sample + "_R" + str(mate) + ".fastq.gz"
            path = run / project / filename
            path.write_bytes(gzip.compress(("@synthetic\n" + "A" * length + "\n+\n" + "I" * length + "\n").encode(), mtime=0))
            manifest.append(hashlib.md5(path.read_bytes()).hexdigest() + "  " + project + "/" + filename + "\n")
        (run / ("md5sum_" + project + "_fastq.txt")).write_text("".join(manifest))
    return run, (sa, fa, sb, fb)


def workdir(path):
    workflow = path / "src/gcf-workflows"
    workflow.mkdir(parents=True)
    (workflow / "libprep.config").write_text("Alpha SE:\n  workflow: rnaseq\n  library_layout: single\nBeta PE:\n  workflow: chipseq\n  library_layout: paired\n")
    return path


def invoke(run, work, project, extra=()):
    command = [str(Path(sys.executable).parent / "configmaker.py"), str(run), "-p", project, *map(str, extra)]
    return subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=30)


def test_automatic_pair_selection_generates_different_workflows_peps_and_checksums(flowcell, tmp_path):
    run, sources = flowcell
    for project, sample, geometry, organism, workflow in ((A, "ALPHA", [75], "homo_sapiens", "rnaseq"),
                                                        (B, "BETA", [75, 150], "mus_musculus", "chipseq")):
        work = workdir(tmp_path / project)
        result = invoke(run, work, project)
        assert result.returncode == 0, result.stdout + result.stderr
        config = yaml.safe_load((work / "config.yaml").read_text())
        pep = yaml.safe_load((work / "pep/pep_config.yaml").read_text())
        summary = json.loads((work / "configmaker.analysis-summary.json").read_text())
        assert list(config["samples"]) == [sample]
        assert config["project_id"] == [project]
        assert config["read_geometry"] == geometry
        assert config["run_read_geometry"] == [75, 150]
        assert config["organism"] == organism and config["workflow"] == workflow
        assert workflow + "/" + workflow + ".smk" in (work / "Snakefile").read_text()
        assert all(project in item["path"] for item in config["metadata_inputs"])
        assert pep["read_geometry"] == geometry and pep["run_read_geometry"] == [75, 150]
        assert pep["metadata_inputs"] == config["metadata_inputs"]
        assert pep["samplesheet_options"] == config["samplesheet_options"]
        assert pep["samplesheet_options"]["SyntheticOption"] == sample.lower()
        assert pep["libprep_selection"] == config["libprep_selection"]
        assert summary["metadata_inputs"] == config["metadata_inputs"]
        assert summary["project_ids"] == [project]
        assert summary["samplesheet_options"] == config["samplesheet_options"]
        value = config["samples"][sample]
        assert value["R1"].endswith("/" + project + "/" + sample + "_R1.fastq.gz")
        assert value["R1_md5sum"] == hashlib.md5((run / project / (sample + "_R1.fastq.gz")).read_bytes()).hexdigest()


def test_explicit_pair_and_effective_geometry_preserve_physical_assertions(flowcell, tmp_path):
    run, (sa, fa, sb, fb) = flowcell
    work = workdir(tmp_path / "explicit")
    result = invoke(run, work, A, ["--sample-sheet", sa, "--sample-submission-form", fa,
                                  "--effective-read-geometry", "75", "--expected-read-geometry", "75"])
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load((work / "config.yaml").read_text())
    assert config["read_geometry"] == [75] and config["run_read_geometry"] == [75, 150]
    assert list(config["samples"]) == ["ALPHA"]
    assert config["libprep_selection"]["entry"] == "Alpha SE"


def test_native_reports_and_run_info_without_legacy_stats_initialize_project(flowcell, tmp_path):
    run, (sa, fa, sb, fb) = flowcell
    (run / "Stats/Stats.json").unlink()
    (run / "Stats").rmdir()
    (run / "Reports").mkdir()
    (run / "Reports/Demultiplex_Stats.csv").write_text("Lane,SampleID,Reads\n1,ALPHA,1\n")
    work = workdir(tmp_path / "native-reports")
    result = invoke(run, work, A, ["--sample-sheet", sa, "--sample-submission-form", fa,
                                  "--effective-read-geometry", "75", "--expected-read-geometry", "75"])
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load((work / "config.yaml").read_text())
    pep = yaml.safe_load((work / "pep/pep_config.yaml").read_text())
    assert config["read_geometry"] == pep["read_geometry"] == [75]
    assert config["run_read_geometry"] == pep["run_read_geometry"] == [75, 150]
    assert config["workflow"] == "rnaseq"
    assert config["libprep_selection"]["entry"] == "Alpha SE"
    assert list(config["samples"]) == ["ALPHA"]


def test_invalid_present_stats_is_not_hidden_by_valid_run_info(flowcell, tmp_path):
    run, (sa, fa, sb, fb) = flowcell
    (run / "Stats/Stats.json").write_text("{invalid")
    work = workdir(tmp_path / "invalid-legacy-stats")
    result = invoke(run, work, A, ["--sample-sheet", sa, "--sample-submission-form", fa,
                                  "--effective-read-geometry", "75"])
    assert result.returncode == 2
    assert "Stats.json" in result.stderr
    assert not (work / "config.yaml").exists()


def test_invalid_unselected_pair_blocks_automatic_initialization(flowcell, tmp_path):
    run, (sa, fa, sb, fb) = flowcell
    submission_form(fb, [customer_row("OTHER", project=B)])
    work = workdir(tmp_path / "blocked")
    result = invoke(run, work, A)
    assert result.returncode == 2
    assert "sample.missing_metadata" in result.stderr and B in result.stderr
    assert not (work / "config.yaml").exists()
    assert not (work / "data").exists()


def test_multiple_generic_candidates_without_canonical_pair_are_ambiguous(flowcell, tmp_path):
    run, (sa, fa, sb, fb) = flowcell
    sa.rename(run / "SampleSheet_one.csv")
    sb.rename(run / "SampleSheet_two.csv")
    fa.rename(run / "Sample-Submission-Form_one.xlsx")
    fb.rename(run / "Sample-Submission-Form_two.xlsx")
    work = workdir(tmp_path / "ambiguous")
    result = invoke(run, work, A)
    assert result.returncode == 2
    assert "pair.missing_filename_key" in result.stderr
    assert not (work / "data").exists()
