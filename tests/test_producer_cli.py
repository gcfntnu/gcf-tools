"""Installed real producer, independent record oracle and normal PEP consumer."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from producer_fixture import PROJECT, RUN, contents, modern_source, records, write_records


def command(source, config, output, *extra):
    return [str(Path(sys.executable).parent / "create_testdata.py"), str(source),
            "--output", str(output), "--samples", "001,CTRL", "--n-reads", "8",
            "--libprep-config", str(config), "--project-id", PROJECT, "--no-fastq-rename", *extra]


def test_real_installed_producer_and_normal_pep(tmp_path):
    source, config = modern_source(tmp_path / "source with spaces")
    before = contents(source)
    output = tmp_path / RUN
    result = subprocess.run(command(source, config, output), cwd=tmp_path, capture_output=True, text=True, timeout=30)
    (tmp_path / "producer-transcript.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert contents(source) == before
    assert not (output / "bcl.done").exists()
    work = tmp_path / "analysis"
    fixture = Path(__file__).parent / "fixtures/paired"
    shutil.copytree(fixture / "workflow", work / "src/gcf-workflows")
    result = subprocess.run([str(Path(sys.executable).parent / "configmaker.py"), str(output),
                             "--project-id", PROJECT], cwd=work, capture_output=True, text=True, timeout=30)
    (tmp_path / "configmaker-transcript.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    generated = yaml.safe_load((work / "config.yaml").read_text())
    pep = yaml.safe_load((work / "pep/pep_config.yaml").read_text())
    with (work / "pep/sample_table.csv").open() as handle:
        rows = {row["sample_name"]: row for row in csv.DictReader(handle)}
    assert set(generated["samples"]) == set(rows) == {"001", "CTRL"}
    assert generated["read_geometry"] == [75, 150]
    assert generated["libprep_selection"]["entry"] == "Synthetic PE"
    assert generated["workflow"] == "rnaseq"
    assert rows["001"]["External_ID"] == "007"
    for sample in rows:
        ids = []
        for mate in (1, 2):
            key = f"R{mate}"
            relative = f"{RUN}/{PROJECT}/{sample}_{key}.fastq.gz"
            assert generated["samples"][sample][key] == relative
            assert pep["sample_modifiers"]["derive"]["sources"][key].format(**rows[sample]) == relative
            link = work / generated["fastq_dir"] / relative
            produced = output / PROJECT / f"{sample}_{key}.fastq.gz"
            assert link.resolve() == produced
            observed = records(produced)
            original = records(source / PROJECT / produced.name)
            assert len(observed) == 8
            assert all(record in original for record in observed)
            positions = [original.index(record) for record in observed]
            assert positions == sorted(set(positions))
            ids.append([record[0].rsplit("/", 1)[0] for record in observed])
            digest = hashlib.md5(produced.read_bytes()).hexdigest()
            assert rows[sample][key + "_md5sum"] == generated["samples"][sample][key + "_md5sum"] == digest
        assert ids[0] == ids[1]
    summary = json.loads((work / "configmaker.analysis-summary.json").read_text())
    assert summary["sample_count"] == summary["planned_sample_count"] == 2
    assert summary["missing_sample_ids"] == []
    assert contents(source) == before


@pytest.mark.parametrize("damage", ["reordered", "missing_config", "missing_metadata", "missing_mate"])
def test_installed_failures_are_nonzero_and_leave_no_output(tmp_path, damage):
    source, config = modern_source(tmp_path / "source")
    if damage == "reordered":
        path = source / PROJECT / "001_R2.fastq.gz"
        write_records(path, list(reversed(records(path))))
    elif damage == "missing_config":
        config.unlink()
    elif damage == "missing_metadata":
        (source / "Sample-Submission-Form.xlsx").unlink()
    else:
        (source / PROJECT / "001_R2.fastq.gz").unlink()
    before = contents(source)
    output = tmp_path / "output"
    result = subprocess.run(command(source, config, output), cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "Testdata producer failed:" in result.stderr
    assert "offline checks prohibit" not in result.stderr
    assert not output.exists()
    assert contents(source) == before
    assert not list(tmp_path.glob(".*-stage-*"))


def test_two_installed_invocations_cannot_replace_each_other(tmp_path):
    source, config = modern_source(tmp_path / "source")
    output = tmp_path / "output"
    processes = [subprocess.Popen(command(source, config, output), cwd=tmp_path,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [process.communicate(timeout=30) for process in processes]
    assert sorted(process.returncode for process in processes) == [0, 1], results
    assert len(records(output / PROJECT / "001_R1.fastq.gz")) == 8
    assert not list(tmp_path.glob(".*-stage-*"))
    before = contents(output)
    result = subprocess.run(command(source, config, output), cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and "Destination already exists" in result.stderr
    assert contents(output) == before


def test_installed_module_form_generates_same_output(tmp_path):
    source, config = modern_source(tmp_path / "source")
    outputs = [tmp_path / "script", tmp_path / "module"]
    commands = [command(source, config, outputs[0]),
                [sys.executable, "-m", "testdata.create_testdata", *command(source, config, outputs[1])[1:]]]
    for argv in commands:
        result = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    assert contents(outputs[0]) == contents(outputs[1])
