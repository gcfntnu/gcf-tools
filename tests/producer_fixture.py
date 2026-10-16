"""Small, wholly synthetic modern metadata-plus-paired-FASTQ source."""
from pathlib import Path
import gzip
import shutil

RUN = "990101_SYNTHETIC_0001_ASYNTHETIC"
PROJECT = "GCF-2099-001"


def modern_source(destination):
    fixture = Path(__file__).parent / "fixtures/paired"
    shutil.copytree(fixture / RUN, destination)
    config = destination.parent / "libprep.yaml"
    shutil.copy2(fixture / "workflow/libprep.config", config)
    return destination, config


def contents(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def records(path):
    """Independent record oracle; never imports producer parsing/sampling."""
    lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
    assert len(lines) % 4 == 0
    result = []
    for start in range(0, len(lines), 4):
        header, sequence, plus, quality = lines[start:start + 4]
        assert header.startswith("@")
        assert plus == "+"
        assert len(sequence) == len(quality) > 0
        assert set(sequence) <= set("ACGTN")
        assert all(33 <= ord(char) <= 126 for char in quality)
        result.append((header, sequence, plus, quality))
    return result


def write_records(path, rows):
    path.write_bytes(gzip.compress(("\n".join(line for row in rows for line in row) + "\n").encode(), mtime=0))
