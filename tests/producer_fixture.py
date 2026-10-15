"""Wholly synthetic legacy-shaped source; markers have no operational meaning."""
from pathlib import Path
import shutil


RUN = "990101_SYNTHETIC_0001_ASYNTHETIC"
PROJECT = "GCF-2099-001"


def legacy_source(destination):
    fixture = Path(__file__).parent / "fixtures/paired"
    shutil.copytree(fixture / RUN, destination)
    sheet = destination / "SampleSheet.csv"
    sheet.write_text(sheet.read_text().replace("ExperimentName,Synthetic paired example",
                                              "ExperimentName," + PROJECT))
    # Characterize the old producer's obsolete dependencies, not manager state.
    (destination / "bcl.done").write_text("synthetic placeholder, never BFQ state\n")
    (destination / "InterOp").mkdir()
    (destination / "InterOp/placeholder.txt").write_text("synthetic; no instrument metrics\n")
    (destination / (PROJECT + "_samplesheet.tsv")).write_text("Sample_ID\n001\n001A\nCTRL\n")
    config = destination.parent / "libprep.yaml"
    shutil.copy2(fixture / "workflow/libprep.config", config)
    return destination, config


def contents(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
