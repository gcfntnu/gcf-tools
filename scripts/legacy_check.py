"""Git-only historical initialization matrix, with reviewed local kit stubs.

Python 3.8-compatible; also callable through the 3.11 development runner.
No scientific workflows are downloaded or executed.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KITS = '''QIAseq 16S ITS Region Panels PE:
  workflow: microbiome
  library_layout: paired
10X Genomics Chromium Single Cell 3p GEM Library & Gel Bead Kit v3 PE:
  workflow: singlecell
  library_layout: paired
Lexogen SENSE Total RNA-Seq Library Prep Kit (w/RiboCop rRNA Depletion Kit V1.2) SE:
  workflow: rnaseq
  library_layout: single
'''


def main():
    assert getattr(sys, "_gcf_offline_guard", False), "Run with the documented offline guard"
    if not (ROOT / ".tests/configmaker").is_dir():
        raise SystemExit("Legacy matrix requires Git-only historical inputs; sdist supports check tests/all")
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    for script, module in (("configmaker.py", "configmaker.configmaker"), ("create_testdata.py", "testdata.create_testdata")):
        for command in ([str(Path(sys.executable).parent / script), "--help"], [sys.executable, "-m", module, "--help"]):
            subprocess.run(command, cwd=work, check=True, stdout=subprocess.DEVNULL)
    spec = importlib.util.spec_from_file_location("prepare_cli_fixtures", ROOT / "tests/prepare_cli_fixtures.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    fixtures = work / "fixtures"
    helper.prepare(ROOT / ".tests/configmaker", fixtures)
    first = fixtures / "201019_M03942_0354_000000000-CVF53"
    second = fixtures / "201020_M03942_0355_000000000-CVF55"
    rna = fixtures / "201109_NB501038_0241_AH2JYJBGXG"
    scenarios = [
        ("fastq-dir", [first]), ("multiple-runs", [first, second]),
        ("keep-batch", [first, second, "--keep-batch"]), ("microbiome", [first]),
        ("single-cell", [fixtures / "201022_NB501038_0238_AHKWNTBGXG"]),
        ("rna", [rna]), ("descriptors", [rna, "--sample-submission-form", rna / "test_descriptor_headers.xlsx"]),
    ]
    for name, args in scenarios:
        cwd = work / name
        workflow = cwd / "src/gcf-workflows"
        workflow.mkdir(parents=True)
        (workflow / "libprep.config").write_text(KITS)
        command = [str(Path(sys.executable).parent / "configmaker.py"), *map(str, args)]
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        (cwd / "command.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(name + ": " + result.stderr)
        assert (cwd / "config.yaml").is_file() and (cwd / "pep/pep_config.yaml").is_file()
        print("Historical initialization passed: " + name)


if __name__ == "__main__":
    main()
