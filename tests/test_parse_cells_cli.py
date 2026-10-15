"""Installed script/module workers and normal configmaker/PEP; no workflows."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from parse_fixture import parse_source
from producer_fixture import PROJECT, RUN, contents, records


def command(fixture, output, module=False):
    prefix = [sys.executable, "-m", "testdata.create_testdata"] if module else [str(Path(sys.executable).parent / "create_testdata.py")]
    return prefix + [str(fixture[0]), "--project-id", PROJECT, "--libprep-config", str(fixture[1]),
                     "--parse-cells", str(fixture[2]), "--output", str(output)]


def test_parse_installed_workers_then_normal_pep(tmp_path):
    fixture = parse_source(tmp_path / "input")
    before = contents(fixture[0])
    outputs = []
    for mode in (False, True):
        parent = tmp_path / ("module" if mode else "script");parent.mkdir()
        output = parent / RUN
        result = subprocess.run(command(fixture, output, module=mode), cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr.count("complete; scanned 24 pairs; retained 18") == 2
        outputs.append(output)
    assert contents(outputs[0]) == contents(outputs[1])
    assert contents(fixture[0]) == before
    for library, expected in fixture[4].items():
        for mate in (1, 2):
            observed = records(outputs[0] / PROJECT / (library + "_R{}.fastq.gz".format(mate)))
            assert [row[0].rsplit("/", 1)[0] for row in observed] == expected
    work = tmp_path / "analysis"
    shutil.copytree(fixture[3] / "src", work / "src")
    result = subprocess.run([str(Path(sys.executable).parent / "configmaker.py"), str(outputs[0]), "--project-id", PROJECT],
                            cwd=work, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load((work / "config.yaml").read_text())
    assert set(config["samples"]) == {"001", "001A"}
    assert set(config["wells"]) == {"001", "1"}
    assert config["wells"]["001"]["Wells"] == "A1,A2"
    assert config["wells"]["1"]["Wells"] == "B1-B2"
    assert config["quant"]["method"] == "splitpipe"
    assert config["quant"]["kit"] == "WT" and config["quant"]["chemistry"] == "v4"
    pep = yaml.safe_load((work / "pep/pep_config.yaml").read_text())
    table = list(csv.DictReader((work / "pep/sample_table.csv").open()))
    for row in table:
        for mate in ("R1", "R2"):
            relative = pep["sample_modifiers"]["derive"]["sources"][mate].format(**row)
            actual = work / config["fastq_dir"] / relative
            assert actual.is_file()
            assert config["samples"][row["sample_name"]][mate] == relative
            assert hashlib.md5(actual.read_bytes()).hexdigest() == row[mate + "_md5sum"]
    assert contents(fixture[0]) == before


@pytest.mark.parametrize("extra", [["--n-reads", "1000"], ["--n-samples", "3"], ["--samples", "001"],
                                    ["--seed", "123456"], ["--n-samp", "3"]])
def test_parse_cli_conflicting_modes_are_explicit_failures(tmp_path, extra):
    fixture = parse_source(tmp_path / "input")
    result = subprocess.run(command(fixture, tmp_path / "output") + extra, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "--parse-cells" in result.stderr
    assert not (tmp_path / "output").exists()


def test_parse_cli_worker_failure_preserves_source_and_cleans_stage(tmp_path):
    fixture = parse_source(tmp_path / "input")
    selection = json.loads(fixture[2].read_text());selection["minimum_signal_pairs"] = 999
    fixture[2].write_text(json.dumps(selection))
    before = contents(fixture[0])
    result = subprocess.run(command(fixture, tmp_path / "output"), cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and "minimum_signal_pairs" in result.stderr
    assert contents(fixture[0]) == before
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".*-stage-*"))
