"""Ensure the documented runner also protects normal Python subprocesses."""
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get("GCF_DEV_OFFLINE") != "1", reason="runner-only guard")
@pytest.mark.parametrize("operation", [
    "socket.create_connection(('127.0.0.1', 12345))",
    "smtplib.SMTP('127.0.0.1', 12345)",
    "smtplib.SMTP_SSL('127.0.0.1', 12345)",
    "importlib.reload(smtplib).SMTP('127.0.0.1', 12345)",
    "subprocess.run(['git', 'clone', 'https://invalid.example/workflows'])",
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
