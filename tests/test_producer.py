"""Inspection and mocked command boundaries; these do not prove FASTQ output."""
import io
from pathlib import Path

import pytest
import yaml

from testdata import create_testdata as producer
from producer_fixture import PROJECT, contents, legacy_source


@pytest.fixture
def source(tmp_path):
    return legacy_source(tmp_path / "source")


def test_parser_preserves_options_and_adds_local_config():
    args = producer.create_argparser().parse_args([
        "source", "--output", "result", "--samples", "001,CTRL",
        "--n-reads", "8", "--n-samples", "2", "--no-fastq-rename",
        "--libprep-config", "kits.yaml", "--verbose"])
    assert vars(args) == dict(runfolder="source", output="result", samples="001,CTRL",
                             n_reads=8, n_samples=2, no_fastq_rename=True,
                             libprep_config="kits.yaml", verbose=True)
    defaults = producer.create_argparser().parse_args(["source"])
    assert (defaults.n_reads, defaults.n_samples, defaults.libprep_config) == (1000, 3, None)


def test_local_config_has_absolute_precedence_and_inspection_preserves_source(source, monkeypatch, tmp_path):
    run, config = source
    before = contents(run)
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / ".libprep.config"
    marker.write_text("existing cwd file\n")
    def forbidden(*args, **kwargs):
        pytest.fail("explicit config must never download")
    monkeypatch.setattr(producer, "urlopen", forbidden)
    inspected = producer.BFQoutput(str(run), libprep_config=config)
    assert inspected.pipeline == "rnaseq"
    assert set(inspected.fastq_files) == {"001", "001A", "CTRL"}
    assert marker.read_text() == "existing cwd file\n"
    assert contents(run) == before
    config.unlink()
    with pytest.raises(FileNotFoundError):
        producer.BFQoutput(str(run), libprep_config=config)


def test_implicit_remote_source_is_characterized_without_network(monkeypatch, tmp_path):
    calls = []
    def download(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(b"Synthetic PE:\n  workflow: rnaseq\n")
    monkeypatch.setattr(producer, "urlopen", download)
    monkeypatch.chdir(tmp_path)
    assert producer.load_libprep_config() == {"Synthetic PE": {"workflow": "rnaseq"}}
    assert calls == [(producer.libprepconf_url, 30)]
    assert list(tmp_path.iterdir()) == []


def test_yaml_regression_preserves_se_first_selection(source):
    run, config = source
    config.write_text("Synthetic PE:\n  workflow: paired\nSynthetic SE:\n  workflow: first\n")
    assert producer.BFQoutput(str(run), libprep_config=config).pipeline == "first"


@pytest.mark.parametrize("content,error", [("- not a mapping\n", ValueError),
                                            ("!!python/object/apply:os.system ['false']", yaml.YAMLError)])
def test_yaml_rejects_wrong_shape_and_python_objects(tmp_path, content, error):
    config = tmp_path / "kits.yaml"
    config.write_text(content)
    with pytest.raises(error):
        producer.load_libprep_config(config)


def test_missing_binary_is_actionable(monkeypatch):
    monkeypatch.setattr(producer.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="seqkit.*missing from PATH"):
        producer.require_tool("seqkit")


def test_command_boundary_returns_both_failures_without_shell(tmp_path, monkeypatch):
    calls = []
    class Reader:
        stdout = io.BytesIO(b"synthetic input")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def wait(self):
            return 7
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Reader()
    def call(command, **kwargs):
        calls.append((command, kwargs))
        return 9
    monkeypatch.setattr(producer, "require_tool", lambda name: "/synthetic/bin/" + name)
    monkeypatch.setattr(producer.subprocess, "Popen", popen)
    monkeypatch.setattr(producer.subprocess, "call", call)
    output = tmp_path / "output.fastq"
    assert producer.sample_fastq("input with spaces.fastq.gz", str(output), 8) == (7, 9)
    assert calls[0][0] == ["/synthetic/bin/gzip", "-cd", "--", "input with spaces.fastq.gz"]
    assert calls[1][0] == ["/synthetic/bin/seqkit", "sample", "-n", "8", "-s", "123456"]
    assert all("shell" not in kwargs for _, kwargs in calls)
    assert output.read_bytes() == b""  # A mock is not sampling evidence.


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: TSV inference loses leading-zero identities")
def test_pending_64_preserves_numeric_sample_identity(source):
    run, config = source
    (run / (PROJECT + "_samplesheet.tsv")).write_text("Sample_ID\n001\n")
    assert list(producer.BFQoutput(str(run), libprep_config=config).fastq_files) == ["001"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: exact IDs must not match another sample prefix")
def test_pending_64_matches_exact_sample(source):
    run, config = source
    files = producer.BFQoutput(str(run), libprep_config=config).fastq_files["001"]
    assert set(files) == {"001_R1.fastq.gz", "001_R2.fastq.gz"}


def mocked_sampling(monkeypatch, returncode=(0, 0)):
    calls = []
    def sample(source, destination, reads):
        calls.append((source, destination, reads))
        return returncode
    monkeypatch.setattr(producer, "sample_fastq", sample)
    monkeypatch.setattr(producer, "compress_fastqs", lambda *args, **kwargs: 0)
    return calls


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: lane filenames currently collapse onto the same R2 output")
def test_pending_64_rejects_filename_collisions(source, tmp_path, monkeypatch):
    run, config = source
    for mate in (1, 2):
        old = run / PROJECT / f"CTRL_R{mate}.fastq.gz"
        old.rename(old.with_name(f"CTRL_S1_L001_R{mate}_001.fastq.gz"))
    calls = mocked_sampling(monkeypatch)
    producer.BFQoutput(str(run), libprep_config=config).sample(str(tmp_path / "result"), samples="CTRL")
    assert len({destination for _, destination, _ in calls}) == 2


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: caller ignores external command failure statuses")
def test_pending_64_propagates_command_failure(source, tmp_path, monkeypatch):
    run, config = source
    mocked_sampling(monkeypatch, returncode=(7, 9))
    try:
        producer.BFQoutput(str(run), libprep_config=config).sample(str(tmp_path / "result"), samples="CTRL")
    except RuntimeError:
        return
    assert False, "failed external command was accepted"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#64: output is deleted before sample validation")
def test_pending_64_preserves_destination_on_invalid_selection(source, tmp_path, monkeypatch):
    run, config = source
    mocked_sampling(monkeypatch)
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep.txt").write_text("owned synthetic sentinel")
    before = contents(output)
    with pytest.raises(AssertionError):
        producer.BFQoutput(str(run), libprep_config=config).sample(str(output), samples="ABSENT")
    assert contents(output) == before
