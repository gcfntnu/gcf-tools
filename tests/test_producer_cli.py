"""Installed producer with real, pinned tools; no mocks of FASTQ processing."""
import gzip
from pathlib import Path
import subprocess
import sys

import pytest

from producer_fixture import PROJECT, contents, legacy_source


def records(path):
    lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
    assert len(lines) % 4 == 0
    output = []
    for index in range(0, len(lines), 4):
        header, sequence, plus, quality = lines[index:index + 4]
        assert header.startswith("@synthetic:CTRL:")
        assert plus == "+"
        assert len(sequence) == len(quality)
        assert set(sequence) <= set("ACGT")
        output.append((header, sequence, plus, quality))
    return output


def run_producer(tmp_path, source, config, reads=8):
    output = tmp_path / "result"
    command = [str(Path(sys.executable).parent / "create_testdata.py"), str(source),
               "--output", str(output), "--samples", "CTRL", "--n-reads", str(reads),
               "--libprep-config", str(config)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    (tmp_path / "producer-transcript.txt").write_text(result.stdout + result.stderr)
    return result, output


def test_real_installed_producer_smoke(tmp_path):
    for name, args, expected in [("seqkit", ["version"], "seqkit v2.10.1"),
                                 ("gzip", ["--version"], "gzip 1.12")]:
        result = subprocess.run([str(Path(sys.executable).parent / name), *args],
                                capture_output=True, text=True, check=True)
        assert result.stdout.splitlines()[0] == expected
    source, config = legacy_source(tmp_path / "source")
    before = contents(source)
    result, output = run_producer(tmp_path, source, config)
    assert result.returncode == 0, result.stdout + result.stderr
    assert contents(source) == before
    assert not (tmp_path / ".libprep.config").exists()
    assert sorted(p.name for p in (output / PROJECT).iterdir()) == [
        "CTRL_S1_R1_001.fastq.gz", "CTRL_S1_R2_001.fastq.gz"]
    selected = []
    for mate in (1, 2):
        observed = records(output / PROJECT / f"CTRL_S1_R{mate}_001.fastq.gz")
        original = records(source / PROJECT / f"CTRL_R{mate}.fastq.gz")
        assert len(observed) == 8
        assert all(record in original for record in observed)
        assert [original.index(record) for record in observed] == sorted(original.index(record) for record in observed)
        assert all(record[0].endswith(f"/{mate}") for record in observed)
        assert all(len(record[1]) == (75 if mate == 1 else 150) for record in observed)
        selected.append([record[0].rsplit("/", 1)[0] for record in observed])
    assert selected[0] == selected[1]
    sheet = (output / "SampleSheet.csv").read_text()
    assert "CTRL," in sheet and "001," not in sheet and "001A," not in sheet
    assert (output / "Stats/Stats.json").read_bytes() == (source / "Stats/Stats.json").read_bytes()
    assert (output / "Sample-Submission-Form.xlsx").read_bytes() == (source / "Sample-Submission-Form.xlsx").read_bytes()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: equal per-file seeds do not validate reordered input mates")
def test_pending_64_real_producer_rejects_reordered_pairs(tmp_path):
    source, config = legacy_source(tmp_path / "source")
    second = source / PROJECT / "CTRL_R2.fastq.gz"
    original = records(second)
    second.write_bytes(gzip.compress(("\n".join(line for record in reversed(original) for line in record) + "\n").encode(), mtime=0))
    before = contents(source)
    result, output = run_producer(tmp_path, source, config, reads=24)
    assert contents(source) == before
    assert result.returncode != 0, "reordered pairs were accepted"


def test_installed_producer_local_config_missing_fails_without_download(tmp_path):
    source, _ = legacy_source(tmp_path / "source")
    result, output = run_producer(tmp_path, source, tmp_path / "missing.yaml")
    assert result.returncode == 1
    assert "No such file" in result.stderr
    assert "offline checks prohibit" not in result.stderr
    assert not output.exists()
