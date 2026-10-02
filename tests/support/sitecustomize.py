"""Test-only offline guard, copied into private venvs by scripts/dev.py.

No source-tree PYTHONPATH. Protect ordinary Python children, including SMTP on
custom ports/reloads. This is a regression guard, not an OS security sandbox.
"""
import os
import sys

if os.environ.get("GCF_DEV_OFFLINE") == "1":
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
            if executable not in allowed and not identity_probe:
                raise RuntimeError("gcf-tools offline checks prohibit executable: " + executable)
            if isinstance(command, (list, tuple)) and any(x in {"-S", "-I"} for x in command):
                raise RuntimeError("gcf-tools offline checks require inherited Python guard")
    sys.addaudithook(offline)
    sys._gcf_offline_guard = True
