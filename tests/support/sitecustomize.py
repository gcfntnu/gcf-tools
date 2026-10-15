"""Test-only offline guard, copied into private venvs by scripts/dev.py.

No source-tree PYTHONPATH. Protect ordinary Python children, including SMTP on
custom ports/reloads. This is a regression guard, not an OS security sandbox.
"""
import os
import sys
import hashlib
import json

if os.environ.get("GCF_DEV_OFFLINE") == "1":
    tool_manifest = os.path.join(sys.prefix, "bin", "producer-tools.json")
    try:
        with open(tool_manifest) as handle:
            tool_hashes = json.load(handle)
        if not isinstance(tool_hashes, dict):
            tool_hashes = {}
    except (OSError, ValueError):
        # A broken optional tool manifest must never disable the audit hook.
        tool_hashes = {}

    def producer_command(executable, command):
        """Allow only pinned local binaries with the producer's fixed operations."""
        if not isinstance(command, (list, tuple)) or not command or command[0] != executable:
            return False
        name = os.path.basename(executable)
        if name not in {"seqkit", "gzip"} or executable != os.path.join(sys.prefix, "bin", name):
            return False
        with open(executable, "rb") as handle:
            if hashlib.sha256(handle.read()).hexdigest() != tool_hashes.get(name):
                return False
        args = list(command[1:])
        if name == "seqkit":
            return args == ["version"] or (len(args) == 5 and args[:2] == ["sample", "-n"]
                    and str(args[2]).isdigit() and args[3:] == ["-s", "123456"])
        return args == ["--version"] or (len(args) == 3 and args[:2] == ["-cd", "--"]) or (
            len(args) >= 2 and args[0] == "--")

    def offline(event, args):
        if event.startswith("smtplib.") or event in {
            "socket.connect", "socket.connect_ex", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.gethostbyaddr", "os.system",
            "os.posix_spawn", "os.spawn", "os.exec",
        }:
            raise RuntimeError("gcf-tools offline checks prohibit network/email/shell: " + event)
        if event == "subprocess.Popen":
            executable = os.fsdecode(args[0])
            command = args[1]
            # Only the checked interpreter and installed scripts may spawn.
            allowed = {sys.executable, os.path.join(sys.prefix, "bin", "configmaker.py"),
                       os.path.join(sys.prefix, "bin", "create_testdata.py")}
            # pip/platform read OS identity through these fixed local probes.
            identity_probe = tuple(command) in {("lsb_release", "-a"), ("uname", "-rs"), ("uname", "-p")}
            if executable not in allowed and not identity_probe and not producer_command(executable, command):
                raise RuntimeError("gcf-tools offline checks prohibit executable: " + executable)
            if isinstance(command, (list, tuple)) and any(x in {"-S", "-I"} for x in command):
                raise RuntimeError("gcf-tools offline checks require inherited Python guard")
    sys.addaudithook(offline)
    sys._gcf_offline_guard = True
