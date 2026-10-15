"""Ensure the documented runner also protects normal Python subprocesses."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("GCF_DEV_OFFLINE") != "1", reason="runner-only guard")
@pytest.mark.parametrize("operation", [
    "socket.create_connection(('127.0.0.1', 12345))",
    "smtplib.SMTP('127.0.0.1', 12345)",
    "smtplib.SMTP_SSL('127.0.0.1', 12345)",
    "importlib.reload(smtplib).SMTP('127.0.0.1', 12345)",
    "subprocess.run(['git', 'clone', 'https://invalid.example/workflows'])",
    "subprocess.run('true', shell=True)",
    "subprocess.run([sys.prefix + '/bin/seqkit', 'version', '--check-update'])",
    "subprocess.run([sys.prefix + '/bin/gzip', '--help'])",
])
def test_child_network_and_mail_are_blocked(tmp_path, operation):
    code = "\n".join([
        "import importlib, smtplib, socket, subprocess, sys",
        "assert getattr(sys, '_gcf_offline_guard', False)",
        "try:", "    " + operation,
        "except RuntimeError as error:",
        "    assert 'gcf-tools offline checks' in str(error)",
        "else:", "    raise AssertionError('guard did not block operation')",
    ])
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.environ.get("GCF_DEV_OFFLINE") != "1", reason="runner-only guard")
def test_copied_or_modified_tool_is_not_allowed(tmp_path):
    # A file with an allowed name outside the pinned venv is never executable.
    tool = tmp_path / "gzip"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    with pytest.raises(RuntimeError, match="prohibit executable"):
        subprocess.run([str(tool), "--version"])

    # Exercise hash validation without changing any provisioned binary.
    import sitecustomize
    original = sitecustomize.tool_hashes["gzip"]
    sitecustomize.tool_hashes["gzip"] = "wrong digest"
    try:
        with pytest.raises(RuntimeError, match="prohibit executable"):
            subprocess.run([sys.prefix + "/bin/gzip", "--version"])
    finally:
        sitecustomize.tool_hashes["gzip"] = original


@pytest.mark.skipif(os.environ.get("GCF_DEV_OFFLINE") != "1", reason="runner-only guard")
@pytest.mark.parametrize("manifest", ["{broken", "[]", "null", None])
def test_broken_optional_tool_manifest_does_not_disable_guard(tmp_path, manifest):
    import sitecustomize
    guard = tmp_path / "guard.py"
    guard.write_text(Path(sitecustomize.__file__).read_text())
    (tmp_path / "bin").mkdir()
    if manifest is not None:
        (tmp_path / "bin/producer-tools.json").write_text(manifest)
    code = "\n".join([
        "import runpy, sys",
        "sys.prefix = sys.argv[1]",
        "sys._gcf_offline_guard = False",
        "namespace = runpy.run_path(sys.argv[2])",
        "assert sys._gcf_offline_guard",
        "assert namespace['tool_hashes'] == {}",
        "try:",
        "    namespace['offline']('smtplib.connect', ())",
        "except RuntimeError as error:",
        "    assert 'prohibit network/email/shell' in str(error)",
        "else:",
        "    raise AssertionError('new guard did not block email')",
    ])
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path), str(guard)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
