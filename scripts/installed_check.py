"""Run using the interpreter being inspected, outside all source checkouts."""
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys


def check(mode, source, expected):
    assert getattr(sys, "_gcf_offline_guard", False), "offline guard not loaded"
    assert not __import__('os').environ.get('PYTHONPATH'), "source path injection"
    root = Path(source).resolve()
    for name in ["configmaker", "configmaker.configmaker", "configmaker.validation",
                 "configmaker.libprep", "descriptors", "descriptors.fuzzmatch",
                 "peppy_support", "testdata.create_testdata"]:
        module = importlib.import_module(name)
        location = Path(module.__file__).resolve()
        if mode == "wheel":
            assert Path(sys.prefix).resolve() in location.parents, (name, location)
            assert root not in location.parents, (name, location)
        else:
            assert root in location.parents, (name, location)
    from configmaker import __version__
    from configmaker.validation import VALIDATOR_VERSION, VALIDATION_API_VERSION, validate_inputs
    from configmaker.libprep import LibprepConfig, LibprepSelection, LibprepConfigError, find_read_geometry
    from configmaker.configmaker import SEQUENCERS, add_workflow, sample_submission_form_parser
    from descriptors.fuzzmatch import ORG_DB
    from descriptors import fuzzmatch_organism
    from peppy_support import conifg2sampletable, create_peppy
    assert __version__ == VALIDATOR_VERSION == importlib.metadata.version("gcf-tools") == "0.3.0"
    assert VALIDATION_API_VERSION == 1
    assert "NB501038" in SEQUENCERS and callable(validate_inputs) and callable(add_workflow)
    assert "homo_sapiens" in ORG_DB and fuzzmatch_organism("homo_sapiens") == "homo_sapiens"
    import descriptors
    resources = Path(descriptors.__file__).parent
    for filename, digest in json.loads(Path(expected).read_text()).items():
        assert hashlib.sha256((resources / filename).read_bytes()).hexdigest() == digest, filename
    print("Installed imports, version/API and resource bytes passed (" + mode + ")")


if __name__ == "__main__":
    check(*sys.argv[1:])
