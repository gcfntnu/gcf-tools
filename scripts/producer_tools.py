"""Pinned Linux x86-64 producer tools, acquired only by development setup."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import tarfile
from urllib.request import urlopen


TOOLS = {
    "seqkit": {
        "version": "seqkit v2.10.1",
        "url": "https://github.com/shenwei356/seqkit/releases/download/v2.10.1/seqkit_linux_amd64.tar.gz",
        "archive": "seqkit_linux_amd64.tar.gz",
        "sha256": "38c5603e51c3d312b62cbfcb55e8511cf6d8280a42f8e824da32cf9224a775b3",
        "member": "seqkit",
        "binary_sha256": "ea5aef8dbe3d85130b84dda77c89e71f1817da1f90353b879337aa81464f214f",
    },
    "gzip": {
        "version": "gzip 1.12",
        "url": "https://conda.anaconda.org/conda-forge/linux-64/gzip-1.12-h166bdaf_0.tar.bz2",
        "archive": "gzip-1.12-h166bdaf_0.tar.bz2",
        "sha256": "9a233d5f734f2a4bed786041a9823b69dad5b6757d84341e9f5c822ec89f083b",
        "member": "bin/gzip",
        "binary_sha256": "91802eb9c35dc069cb781b50b7c900877e5cfeb56d56d943c5ebb782a818d48b",
    },
}


def verify(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Producer tool checksum mismatch: " + str(path))


def acquire(destination, source=None):
    if platform.machine() != "x86_64":
        raise RuntimeError("Pinned producer tools currently require Linux x86-64")
    destination.mkdir()
    for spec in TOOLS.values():
        target = destination / spec["archive"]
        if source:
            shutil.copy2(Path(source) / spec["archive"], target)
        else:
            print("Acquire producer tool: " + spec["url"], flush=True)
            with urlopen(spec["url"], timeout=60) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
        verify(target, spec["sha256"])
    (destination / "identity.json").write_text(json.dumps(TOOLS, indent=2) + "\n")


def install(archives, python):
    for name, spec in TOOLS.items():
        archive = Path(archives) / spec["archive"]
        verify(archive, spec["sha256"])
        with tarfile.open(archive) as handle:
            # Extract exactly one regular member, never paths/symlinks from tar.
            member = handle.getmember(spec["member"])
            if not member.isfile():
                raise RuntimeError("Producer tool archive member is not a regular file")
            target = python.parent / name
            target.write_bytes(handle.extractfile(member).read())
            target.chmod(0o755)
            verify(target, spec["binary_sha256"])
    guard_hashes = {name: spec["binary_sha256"] for name, spec in TOOLS.items()}
    (python.parent / "producer-tools.json").write_text(json.dumps(guard_hashes) + "\n")


def verify_installed(python):
    expected = {name: spec["binary_sha256"] for name, spec in TOOLS.items()}
    try:
        manifest = json.loads((python.parent / "producer-tools.json").read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError("Producer tool manifest is invalid; rerun setup") from error
    if manifest != expected:
        raise RuntimeError("Producer tool manifest changed; rerun setup")
    for name, spec in TOOLS.items():
        verify(python.parent / name, spec["binary_sha256"])
