#!/usr/bin/env python3
"""Isolated Linux/Python 3.11 setup and offline checks; see docs/development.md."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT.parent / (ROOT.name + "-local")
BASELINE = ROOT / "requirements-dev.txt"
PACKAGES = ("configmaker", "descriptors", "peppy_support", "testdata")
CLI = tuple(sorted(p.name for p in (ROOT / "tests").glob("test_*_cli.py")))
FAST = tuple(sorted(p.name for p in (ROOT / "tests").glob("test_*.py") if p.name not in CLI))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(command, env, cwd, log=None):
    command = list(map(str, command))
    print("+ " + shlex.join(command), flush=True)
    if log is None:
        subprocess.run(command, env=env, cwd=cwd, check=True)
    else:
        with log.open("w") as output:
            process = subprocess.Popen(command, env=env, cwd=cwd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                print(line, end="", flush=True)
                output.write(line)
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, command)


def environment(work, python, offline=True):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("PYTHON", "PIP_", "UV_", "GCF_DEV_", "PYTEST_")) or key in {"VIRTUAL_ENV", "CONDA_PREFIX"}:
            # Ordinary index/certificate access is allowed only during acquisition.
            if not offline and key in {"PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "PIP_CERT", "PIP_CLIENT_CERT"}:
                continue
            del env[key]
    for key, subdir in (("TMPDIR", "tmp"), ("PIP_CACHE_DIR", "cache/pip"), ("XDG_CACHE_HOME", "cache")):
        path = work / subdir
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(PATH=str(python.parent) + os.pathsep + os.defpath,
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PIP_CONFIG_FILE=os.devnull,
               PIP_DISABLE_PIP_VERSION_CHECK="1")
    if offline:
        env.update(PIP_NO_INDEX="1", GCF_DEV_OFFLINE="1")
    return env


def source_files(root):
    # Explicit distribution boundary: never copy hidden state or historical inputs.
    files = []
    for name in ("pyproject.toml", "setup.py", "MANIFEST.in", "README.md", "CONTRIBUTING.md", "AGENTS.md", "requirements-dev.txt", "requirements-python38.txt"):
        files.append(root / name)
    for directory, suffixes in [(p, {".py", ".yaml", ".pkl"}) for p in PACKAGES] + [
        ("scripts", {".py"}), ("tests", {".py"}), ("docs", {".md"})
    ]:
        files.extend(p for p in (root / directory).rglob("*") if p.is_file()
                     and p.suffix in suffixes and "__pycache__" not in p.parts)
    return sorted(files)


def identity(root):
    identified = source_files(root) + sorted(p for p in (root / ".tests").rglob("*") if p.is_file())
    files = {str(p.relative_to(root)): sha(p) for p in identified}
    result = {"source_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
              "files": files}
    if (root / ".git").exists():
        for key, args in (("commit", ["rev-parse", "HEAD"]), ("status", ["status", "--short"])):
            result[key] = subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    else:
        result["commit"] = "source distribution (no Git metadata)"
    return result


def copy_source(target):
    for file in source_files(ROOT):
        out = target / file.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, out)


@contextmanager
def lock():
    if DEV.is_symlink():
        raise RuntimeError("Refusing symlinked task workspace; use a separate worktree")
    DEV.mkdir(exist_ok=True)
    with (DEV / "lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Setup/check already running here; use another worktree") from None
        yield


def workspace(kind):
    parent = DEV / kind
    parent.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    print("Artifacts: " + str(work), flush=True)
    return work


def install_guard(python):
    # Copy test-only code into this venv. No PYTHONPATH and nothing in the wheel.
    site = python.parent.parent / "lib" / ("python%d.%d" % sys.version_info[:2]) / "site-packages"
    shutil.copy2(ROOT / "tests/support/sitecustomize.py", site / "sitecustomize.py")


def verify_baseline(python, env, work, requirements):
    run([python, ROOT / "scripts/verify_environment.py", requirements], env, work)


def freeze(python, env, work, name="packages.txt"):
    with (work / name).open("w") as output:
        subprocess.run([str(python), "-m", "pip", "list", "--format=freeze"], env=env, cwd=work, stdout=output, check=True)


def setup(args):
    work = workspace("setups")
    python = work / "venv/bin/python"
    env = environment(work, python, offline=False)
    requirements = Path(args.requirements).resolve() if args.requirements else BASELINE
    shutil.copy2(requirements, work / "requirements.txt")
    report = {"source": identity(ROOT), "python": sys.version, "platform": platform.platform(),
              "requirements_origin": str(requirements), "requirements_sha256": sha(requirements),
              "requirements": requirements.read_text(), "acquisition": "local wheels" if args.wheelhouse else "package index"}
    write_json(work / "identity.json", report)
    run([sys.executable, "-m", "venv", python.parent.parent], env, work)
    wheels = work / "wheels"
    command = [python, "-m", "pip", "download", "--only-binary=:all:", "--dest", wheels, "-r", requirements]
    if args.wheelhouse:
        command += ["--no-index", "--find-links", str(Path(args.wheelhouse).resolve())]
    run(command, env, work, work / "acquisition.log")
    install_guard(python)
    env = environment(work, python)
    run([python, "-m", "pip", "install", "--no-index", "--find-links", wheels, "-r", requirements], env, work)
    run([python, "-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", str(ROOT) + "[dev]"], env, work)
    run([python, "-m", "pip", "check"], env, work)
    verify_baseline(python, env, work, requirements)
    freeze(python, env, work)
    state = {"python": str(python), "wheelhouse": str(wheels), "setup": str(work),
             "baseline_sha256": sha(BASELINE), "pyproject_sha256": sha(ROOT / "pyproject.toml"),
             "requirements_sha256": sha(work / "requirements.txt"),
             "wheel_sha256": {p.name: sha(p) for p in sorted(wheels.glob("*.whl"))}}
    write_json(work / "state.json", state)
    pending = DEV / "current.next.json"
    write_json(pending, state)
    pending.replace(DEV / "current.json")
    print("Setup complete; routine checks now use only these local dependencies.")


def load_setup():
    if not (DEV / "current.json").exists():
        raise RuntimeError("Run python3.11 scripts/dev.py setup first")
    state = json.loads((DEV / "current.json").read_text())
    for name, key in ((BASELINE, "baseline_sha256"), (ROOT / "pyproject.toml", "pyproject_sha256")):
        if sha(name) != state[key]:
            raise RuntimeError(name.name + " changed; rerun setup")
    for key in ("python", "wheelhouse", "setup"):
        path = Path(state[key])
        if not path.exists() or not path.parent.resolve().is_relative_to(DEV.resolve()):
            raise RuntimeError("Environment moved/incomplete; rerun setup in this worktree")
    if sha(Path(state["setup"]) / "requirements.txt") != state["requirements_sha256"]:
        raise RuntimeError("Prepared requirements changed; rerun setup")
    actual = {p.name: sha(p) for p in Path(state["wheelhouse"]).glob("*.whl")}
    if actual != state["wheel_sha256"]:
        raise RuntimeError("Prepared dependency wheels changed; rerun setup")
    return state


def tests(python, env, work, root, profile):
    selection = FAST if profile == "fast" else CLI if profile == "cli" else FAST + CLI
    run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", work / "pytest-tmp",
         "--junitxml", work / "tests.xml", *[root / "tests" / p for p in selection]],
        env, work, work / "tests.log")


def smoke(python, env, work, mode, root=ROOT):
    work.mkdir(parents=True, exist_ok=True)
    probe = work / "installed_check.py"
    shutil.copy2(ROOT / "scripts/installed_check.py", probe)
    hashes = work / "resource-hashes.json"
    write_json(hashes, {p.name: sha(p) for p in (ROOT / "descriptors").iterdir() if p.suffix in {".yaml", ".pkl"}})
    run([python, probe, mode, root, hashes], env, work)
    for script, module, option in (("configmaker.py", "configmaker.configmaker", "--libprep-config"),
                                   ("create_testdata.py", "testdata.create_testdata", "--n-reads")):
        for command in ([python.parent / script, "--help"], [python, "-m", module, "--help"]):
            result = subprocess.run(list(map(str, command)), env=env, cwd=work, capture_output=True, text=True, check=True)
            assert option in result.stdout, command
            (work / (script + ("-module" if "-m" in command else "-script") + ".txt")).write_text(result.stdout + result.stderr)
            print("Passed: " + shlex.join(list(map(str, command))))


def inspect_dist(dist, source):
    wheel = next(dist.glob("*.whl"))
    sdist = next(dist.glob("*.tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = set(archive.namelist())
        for package in PACKAGES:
            for file in (source / package).rglob("*"):
                if file.is_file() and file.suffix in {".py", ".yaml", ".pkl"}:
                    relative = str(file.relative_to(source))
                    assert archive.read(relative) == file.read_bytes(), relative
        for script in ("configmaker.py", "create_testdata.py"):
            assert any(p.endswith(".data/scripts/" + script) for p in wheel_files), script
        assert all(p.split('/')[0] in PACKAGES or '.dist-info/' in p or '.data/scripts/' in p for p in wheel_files)
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        assert all(not p.issym() and not p.islnk() for p in members)
        sdist_files = {p.name.split("/", 1)[1] for p in members if p.isfile()}
        expected = {str(p.relative_to(source)) for p in source_files(source)}
        assert expected <= sdist_files, sorted(expected - sdist_files)
        extras = sdist_files - expected
        assert all(p in {"PKG-INFO", "setup.cfg"} or p.startswith("gcf_tools.egg-info/") for p in extras), extras
    assert not any("__pycache__" in p or p.endswith((".pyc", ".log")) for p in wheel_files | sdist_files)
    write_json(dist / "contents.json", {"wheel": sorted(wheel_files), "sdist": sorted(sdist_files),
                                        "sha256": {p.name: sha(p) for p in (wheel, sdist)}})
    print("Wheel/sdist file boundaries and runtime resource bytes passed")
    return wheel, sdist


def distribution_checks(state, work, include_sdist):
    source = work / "build-source"
    copy_source(source)
    python = Path(state["python"])
    env = environment(work, python)
    dist = work / "dist"
    # build's default builds the wheel FROM its freshly generated sdist.
    run([python, "-m", "build", "--no-isolation", "--outdir", dist, source], env, work, work / "build.log")
    wheel, sdist = inspect_dist(dist, source)
    wheel_python = work / "wheel-venv/bin/python"
    wheel_env = environment(work, wheel_python)
    run([sys.executable, "-m", "venv", wheel_python.parent.parent], wheel_env, work)
    install_guard(wheel_python)
    run([wheel_python, "-m", "pip", "install", "--no-index", "--find-links", state["wheelhouse"],
         "-r", Path(state["setup"]) / "requirements.txt", wheel], wheel_env, work)
    run([wheel_python, "-m", "pip", "check"], wheel_env, work)
    verify_baseline(wheel_python, wheel_env, work, Path(state["setup"]) / "requirements.txt")
    freeze(wheel_python, wheel_env, work, "wheel-packages.txt")
    smoke(wheel_python, wheel_env, work / "wheel-smoke", "wheel")
    # Copy only tests, never runtime source: exercise all assertions against wheel.
    test_root = work / "wheel-tests"
    shutil.copytree(ROOT / "tests", test_root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    tests(wheel_python, wheel_env, test_root, test_root, "all")
    if include_sdist:
        extracted = work / "sdist-source"
        extracted.mkdir()
        with tarfile.open(sdist) as archive:
            # Our freshly inspected archive; reject any traversal before extraction.
            for member in archive.getmembers():
                if not (extracted / member.name).resolve().is_relative_to(extracted.resolve()):
                    raise RuntimeError("Unsafe source archive member")
            archive.extractall(extracted)
        root = next(extracted.iterdir())
        # Exercise the exact documented sdist setup/check interface, fresh env.
        run([sys.executable, root / "scripts/dev.py", "setup", "--wheelhouse", state["wheelhouse"],
             "--requirements", Path(state["setup"]) / "requirements.txt"], env, root, work / "sdist-setup.log")
        run([sys.executable, root / "scripts/dev.py", "check", "tests"], env, root, work / "sdist-tests.log")


def check(args):
    state = load_setup()
    work = workspace("runs")
    python = Path(state["python"])
    install_guard(python)
    env = environment(work, python)
    report = {"source": identity(ROOT), "setup": state, "profile": args.profile,
              "python": sys.version, "platform": platform.platform(), "result": "failed",
              "fixtures": "historical Git inputs" if (ROOT / ".tests").exists() else "synthetic sdist SE substitute"}
    write_json(work / "identity.json", report)
    started = time.monotonic()
    try:
        verify_baseline(python, env, work, Path(state["setup"]) / "requirements.txt")
        freeze(python, env, work)
        run([python, "-m", "pip", "check"], env, work)
        smoke(python, env, work / "editable-smoke", "editable")
        if args.profile in ("fast", "cli", "tests", "all"):
            tests(python, env, work, ROOT, args.profile)
        if args.profile in ("wheel", "sdist", "all"):
            distribution_checks(state, work, args.profile in ("sdist", "all"))
        if args.profile == "legacy":
            run([python, ROOT / "scripts/legacy_check.py", work / "legacy"], env, work, work / "legacy.log")
        report["result"] = "passed"
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        write_json(work / "identity.json", report)
    print("Checks passed: " + args.profile + "; evidence: " + str(work))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup_parser = sub.add_parser("setup", help="One-time dependency acquisition and editable install")
    setup_parser.add_argument("--wheelhouse", help="Optional existing wheels for disconnected provisioning; copied privately")
    setup_parser.add_argument("--requirements", help="Explicit development baseline override; recorded, never a production policy")
    check_parser = sub.add_parser("check", help="Repeat offline checks using prepared dependencies")
    check_parser.add_argument("profile", choices=("fast", "cli", "tests", "wheel", "sdist", "all", "legacy"), default="fast", nargs="?")
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 11):
        parser.error("Development reference is Linux/Python 3.11 with venv; this is not a runtime support floor")
    try:
        with lock():
            setup(args) if args.command == "setup" else check(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError, AssertionError) as error:
        parser.exit(1, "Development command failed: " + str(error) + "\nArtifacts retained under " + str(DEV) + "\n")


if __name__ == "__main__":
    main()
