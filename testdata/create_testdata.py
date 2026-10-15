#!/usr/bin/env python
"""Generate a bounded, deterministic paired fixture from BFQ-style source data."""
import argparse
from contextlib import contextmanager
import csv
import ctypes
import errno
import gzip
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import random
import re
import shutil
import stat
import sys
import tempfile
import zlib

if __name__ == "__main__":
    # Installed/legacy egg bin scripts include configmaker.py alongside this
    # script; exclude both wrapper locations so that file cannot shadow package.
    script_dirs = {Path(__file__).resolve().parent, Path(sys.argv[0]).resolve().parent}
    sys.path[:] = [p for p in sys.path if Path(p or os.curdir).resolve() not in script_dirs]

from configmaker import __version__
from configmaker.libprep import LibprepConfig, find_read_geometry
from configmaker.validation import InputValidationError, validate_inputs


_SEQUENCE = re.compile(rb"[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+")
_QUALITY = re.compile(rb"[!-~]+")
_BAD_HEADER = re.compile(rb"[\x00-\x08\x0b-\x1f\x7f-\xff]")
ALGORITHM = "paired-reservoir-v1; Python random.Random(seed), randrange(i+1), source-order output"


def _fingerprint(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _component(value, kind):
    if (not isinstance(value, str) or not value or value in (".", "..")
            or not value.isascii() or any(char.isspace() or not 33 <= ord(char) <= 126
                                         or char in "/\\," for char in value)):
        raise ValueError("{} must be an exact printable ASCII path component without whitespace, commas or separators".format(kind))
    return value


class InputFile:
    """An immutable input identity; FASTQ links are followed, never copied as links."""
    def __init__(self, path, allow_link=False):
        self.path = Path(path).absolute()
        if self.path.is_symlink() and not allow_link:
            raise ValueError("Only FASTQ file symlinks are supported: {}".format(self.path))
        self.resolved = self.path.resolve(strict=True)
        self.link_identity = _fingerprint(self.path.lstat())
        value = self.path.stat()
        if not stat.S_ISREG(value.st_mode):
            raise ValueError("Expected a regular readable input file: {}".format(self.path))
        self.identity = _fingerprint(value)
        self.sha256 = None

    def verify(self):
        try:
            same = (self.path.resolve(strict=True) == self.resolved
                    and _fingerprint(self.path.lstat()) == self.link_identity
                    and _fingerprint(self.path.stat()) == self.identity)
        except OSError:
            same = False
        if not same:
            raise ValueError("Input changed during generation: {}".format(self.path))

    @contextmanager
    def open(self):
        self.verify()
        with self.path.open("rb") as handle:
            if _fingerprint(os.fstat(handle.fileno())) != self.identity:
                raise ValueError("Input changed before reading: {}".format(self.path))
            yield handle
            if _fingerprint(os.fstat(handle.fileno())) != self.identity:
                raise ValueError("Input changed while reading: {}".format(self.path))
        self.verify()

    def read(self):
        with self.open() as handle:
            data = handle.read()
        self.sha256 = hashlib.sha256(data).hexdigest()
        return data

    @contextmanager
    def gzip_stream(self):
        digest = hashlib.sha256()
        with self.open() as handle:
            class HashReader:
                def read(self, size=-1):
                    data = handle.read(size)
                    digest.update(data)
                    return data
            with gzip.GzipFile(fileobj=HashReader(), mode="rb") as stream:
                yield stream
        self.sha256 = digest.hexdigest()


def _record(stream, path, mate, number):
    header = stream.readline()
    if not header:
        return None
    lines = [header] + [stream.readline() for _ in range(3)]
    if not all(lines):
        raise ValueError("Incomplete FASTQ record {} in {}".format(number, path))
    header, sequence, plus, quality = [line.rstrip(b"\r\n") for line in lines]
    context = "record {} in {}".format(number, path)
    if not header.startswith(b"@") or not header[1:] or _BAD_HEADER.search(header):
        raise ValueError("Invalid FASTQ header at " + context)
    tokens = header[1:].split()
    if not tokens or header[1:2].isspace():
        raise ValueError("Missing FASTQ read ID at " + context)
    identity = tokens[0]
    if identity.endswith((b"/1", b"/2")):
        if identity[-1:] != str(mate).encode():
            raise ValueError("Wrong FASTQ mate label at " + context)
        identity = identity[:-2]
    if not identity:
        raise ValueError("Missing FASTQ read ID at " + context)
    if len(tokens) > 1 and re.match(rb"\d+:[YN]:", tokens[1]):
        if tokens[1].split(b":", 1)[0] != str(mate).encode():
            raise ValueError("Wrong Illumina mate label at " + context)
    if not plus.startswith(b"+"):
        raise ValueError("Invalid FASTQ separator at " + context)
    if plus[1:] and plus[1:].split() != tokens:
        raise ValueError("FASTQ separator does not repeat its header at " + context)
    if _SEQUENCE.fullmatch(sequence) is None:
        raise ValueError("Invalid or empty FASTQ sequence at " + context)
    if len(sequence) != len(quality) or _QUALITY.fullmatch(quality) is None:
        raise ValueError("Invalid FASTQ quality or length at " + context)
    return identity, b"\n".join((header, sequence, plus, quality)) + b"\n"


def paired_records(first, second):
    """Yield validated (read ID, R1 bytes, R2 bytes), reading both complete streams.

    Inputs are InputFile instances. Accepted IDs are identical unlabeled first
    tokens, /1 and /2 suffixes, or Illumina 1:N:... / 2:N:... comments. Any
    explicit mate label must agree with its file. No scientific interpretation.
    """
    try:
        with first.gzip_stream() as r1, second.gzip_stream() as r2:
            number = 0
            while True:
                number += 1
                a = _record(r1, first.path, 1, number)
                b = _record(r2, second.path, 2, number)
                if a is None and b is None:
                    break
                if a is None or b is None:
                    raise ValueError("FASTQ mate counts differ at pair {}".format(number))
                if a[0] != b[0]:
                    raise ValueError("FASTQ mate IDs/order differ at pair {}".format(number))
                yield a[0], a[1], b[1]
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("Cannot read paired gzip FASTQs {} and {}: {}".format(
            first.path, second.path, error)) from error


def sample_pairs(first, second, n_reads, seed):
    """Reservoir-sample pair positions together, validating even discarded reads."""
    rng, reservoir, total = random.Random(seed), [], 0
    for index, record in enumerate(paired_records(first, second)):
        total += 1
        if index < n_reads:
            reservoir.append((index, record))
        else:
            position = rng.randrange(index + 1)
            if position < n_reads:
                reservoir[position] = (index, record)
    if not total:
        raise ValueError("FASTQ pair is empty: {}".format(first.path))
    return sorted(reservoir), total


def _filtered_samplesheet(content, samples, project_id=None):
    selected, section, headers = set(samples), None, None
    result = io.StringIO(newline="")
    writer = csv.writer(result, lineterminator="\n")
    for row in csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True):
        tag = row[0].strip() if row else ""
        if tag.startswith("[") and tag.endswith("]") and all(not cell.strip() for cell in row[1:]):
            section = tag[1:-1].lower()
            writer.writerow(row)
        elif section in ("data", "bclconvert_data") and row and any(cell.strip() for cell in row):
            if headers is None:
                headers = row
                writer.writerow(row)
            else:
                values = dict(zip(headers, row))
                if (values.get("Sample_ID") in selected
                        and (project_id is None or values.get("Sample_Project") == project_id)):
                    writer.writerow(row)
        else:
            writer.writerow(row)
    return result.getvalue().encode("utf-8")


def sample_samplesheet(input_fn, output_fn, samples, valid_samples, project_id=None):
    """Compatibility helper; exact CSV filtering, including BCLConvert_Data.

    valid_samples is retained for call compatibility; the explicit selected IDs
    alone determine the subset. The producer uses its captured validated bytes.
    """
    Path(output_fn).write_bytes(_filtered_samplesheet(Path(input_fn).read_bytes(), samples, project_id))


def publish_noreplace(stage, destination):
    """Atomically publish a sibling directory on Linux, never replacing a rival."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Safe directory publication requires Linux renameat2")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        rename = library.renameat2
    except AttributeError as error:
        raise RuntimeError("Safe publication requires renameat2; destination was not created") from error
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError("Destination already exists; choose a new path: {}".format(destination))
        raise OSError(code, "Cannot publish without replacement: " + os.strerror(code), str(destination))


class BFQoutput:
    """Metadata plus flat paired FASTQs; no assertion of BFQ processing state."""
    def __init__(self, dirname=None, libprep_config=None, project_id=None):
        self.dirname = dirname
        self.libprep_config = libprep_config
        self.pipeline = None
        self.fastq_files = None
        self._archive = None
        self._gcf_number = project_id
        self._fastq_dir = None
        self._inputs, self._directories, self._metadata = [], {}, {}
        self._inspect()

    def _directory(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Expected a directory, not a directory symlink: {}".format(path))
        self._directories[path] = _fingerprint(path.stat())

    def _capture(self, path, allow_link=False):
        item = InputFile(path, allow_link)
        self._inputs.append(item)
        return item

    def _inspect(self):
        if self.dirname is None:
            raise ValueError("A BFQ-style source directory is required")
        _component(self._gcf_number, "Explicit --project-id/project_id")
        if self.libprep_config is None:
            raise ValueError("Explicit local --libprep-config/libprep_config is required; downloads are disabled")
        self._source = Path(self.dirname).resolve(strict=True)
        self._directory(self._source)
        for name in ("SampleSheet.csv", "Sample-Submission-Form.xlsx", "Stats/Stats.json"):
            if name.startswith("Stats/"):
                self._directory(self._source / "Stats")
            item = self._capture(self._source / name)
            self._metadata[name] = item.read()
        result = validate_inputs(self._source / "SampleSheet.csv", self._source / "Sample-Submission-Form.xlsx",
                                 project_ids=[self._gcf_number])
        if not result.ok:
            raise InputValidationError(result)
        for item in self._inputs:
            item.verify()
        for identity in result.to_dict()["inputs"]:
            captured = next(item for item in self._inputs if str(item.path) == identity["path"])
            if captured.sha256 != identity["sha256"]:
                raise ValueError("Metadata changed during validation: {}".format(captured.path))
        config = self._capture(self.libprep_config)
        snapshot = LibprepConfig(str(config.path), config.read())
        geometry = find_read_geometry([self._source])
        if len(geometry) != 2:
            raise ValueError("This producer profile requires paired read geometry")
        self.selection = snapshot.select(result.custom_options.get("Libprep"), geometry)
        self.pipeline = self.selection.workflow
        self._fastq_dir = str(self._source / self._gcf_number)
        self._directory(self._fastq_dir)
        self.fastq_files = {sid: [sid + "_R1.fastq.gz", sid + "_R2.fastq.gz"]
                            for sid in result.samples.Sample_ID}
        self._validation = result
        # Statistics are copied unchanged, with no synthetic count recalculation.
        for name in ("Stats", "InterOp"):
            root = self._source / name
            if not os.path.lexists(root):
                continue
            self._directory(root)
            for directory, subdirs, files in os.walk(root, followlinks=False):
                self._directory(directory)
                for child in subdirs:
                    self._directory(Path(directory) / child)
                for filename in files:
                    path = Path(directory) / filename
                    relative = str(path.relative_to(self._source))
                    if relative not in self._metadata:
                        self._metadata[relative] = self._capture(path).read()
        self._verify_inputs()

    def _verify_inputs(self):
        for item in self._inputs:
            item.verify()
        for path, identity in self._directories.items():
            if path.is_symlink() or not path.is_dir() or _fingerprint(path.stat()) != identity:
                raise ValueError("Input directory changed during generation: {}".format(path))

    def sample(self, output_dir, overwrite=False, n_reads=10000, n_samples=3,
               samples=None, no_fastq_rename=False, seed=123456):
        """Write a new fixture; historical overwrite/automatic/rename paths refuse.

        n_reads remains per mate file (one pair per selected sample). n_samples
        is retained but unused with mandatory explicit samples. Even overwrite=True
        never permits replacement. The complete selected FASTQs are validated.
        """
        if samples is None:
            raise ValueError("Explicit --samples/samples is required; automatic --n-samples selection is unsupported")
        if not no_fastq_rename:
            raise ValueError("This flat paired profile requires --no-fastq-rename/no_fastq_rename=True")
        if type(n_reads) is not int or n_reads <= 0:
            raise ValueError("--n-reads/n_reads must be a positive integer")
        if type(seed) is not int:
            raise ValueError("--seed/seed must be an integer")
        selected = samples.split(",") if isinstance(samples, str) else list(samples)
        if not selected or len(selected) != len(set(selected)):
            raise ValueError("Explicit sample selection must be nonempty without duplicate IDs")
        for sid in selected:
            _component(sid, "Sample ID")
            if sid not in self.fastq_files:
                raise ValueError("Unknown exact sample ID for selected project: {!r}".format(sid))
        selected.sort()
        if output_dir is None:
            raise ValueError("Explicit --output/output_dir is required")
        requested = Path(output_dir).absolute()
        if os.path.lexists(requested):
            raise FileExistsError("Destination already exists; overwrite is unsupported, choose a new path: {}".format(requested))
        parent = requested.parent.resolve(strict=True)
        destination = parent / requested.name
        if not parent.is_dir():
            raise ValueError("Destination parent must be an existing directory")
        if (destination == self._source or destination in self._source.parents
                or self._source in destination.parents):
            raise ValueError("Source and destination must not overlap")
        parent_identity = _fingerprint(parent.stat())[:3]
        # Reject unsupported project layouts instead of guessing names or collapsing lanes.
        known_names = {name for names in self.fastq_files.values() for name in names}
        for path in Path(self._fastq_dir).iterdir():
            if path.is_dir() or (path.name.endswith((".fastq.gz", ".fq.gz", ".fastq", ".fq"))
                                 and path.name not in known_names):
                raise ValueError("Unsupported FASTQ layout or directory in selected project: {}".format(path))
        pairs, seen = {}, set()
        for sid in selected:
            pair = [self._capture(Path(self._fastq_dir) / name, allow_link=True)
                    for name in self.fastq_files[sid]]
            for item in pair:
                if item.resolved == destination or destination in item.resolved.parents:
                    raise ValueError("Destination aliases an input file or FASTQ symlink target")
                if item.identity[:2] in seen:
                    raise ValueError("Selected FASTQs alias the same input file: {}".format(item.path))
                seen.add(item.identity[:2])
            pairs[sid] = pair
        for item in self._inputs:
            if item.resolved == destination or destination in item.resolved.parents:
                raise ValueError("Destination aliases an input file")
        self._verify_inputs()
        retained = {}
        for sid, pair in pairs.items():
            retained[sid] = sample_pairs(*pair, n_reads=n_reads, seed=seed)
        self._verify_inputs()
        stage = None
        try:
            stage = Path(tempfile.mkdtemp(prefix=".{}-stage-".format(destination.name), dir=parent))
            for name, data in self._metadata.items():
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(_filtered_samplesheet(data, selected, self._gcf_number)
                                   if name == "SampleSheet.csv" else data)
            result = validate_inputs(stage / "SampleSheet.csv", stage / "Sample-Submission-Form.xlsx",
                                     project_ids=[self._gcf_number])
            if not result.ok:
                raise InputValidationError(result)
            project = stage / self._gcf_number
            project.mkdir()
            checksums, counts, output_hashes = [], {}, {}
            for sid, (records, total) in retained.items():
                counts[sid] = {"available_pairs": total, "selected_pairs": len(records)}
                for mate in (1, 2):
                    path = project / (sid + "_R{}.fastq.gz".format(mate))
                    with path.open("wb") as handle, gzip.GzipFile(filename="", mode="wb", fileobj=handle,
                                                                  mtime=0, compresslevel=9) as compressed:
                        for _, record in records:
                            compressed.write(record[mate])
                    data = path.read_bytes()
                    relative = str(path.relative_to(stage))
                    checksums.append("{}  {}\n".format(hashlib.md5(data).hexdigest(), relative))
                    output_hashes[relative] = hashlib.sha256(data).hexdigest()
            (stage / "md5sum_{}_fastq.txt".format(self._gcf_number)).write_text("".join(checksums))
            manifest = {"schema_version": 1, "producer": "gcf-tools " + __version__,
                        "profile": "flat-paired-metadata-source", "algorithm": ALGORITHM,
                        "python": sys.version.split()[0], "zlib": zlib.ZLIB_RUNTIME_VERSION,
                        "seed": seed, "requested_pairs_per_sample": n_reads,
                        "project_id": self._gcf_number, "samples": counts,
                        "source_name": self._source.name,
                        "statistics": "Stats and InterOp are unchanged original-source metrics, not subset counts",
                        "workbook": "Complete source workbook retained; extra metadata rows are intentional",
                        "gzip": "mtime=0; no filename; level=9; LF record lines",
                        "libprep": {key: value for key, value in self.selection.diagnostics().items() if key != "source"},
                        "source_sha256": {str(item.path.relative_to(self._source)): item.sha256
                                          for item in self._inputs if self._source in item.path.parents},
                        "output_fastq_sha256": output_hashes}
            (stage / "testdata.provenance.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            self._verify_inputs()
            if parent.resolve(strict=True) != parent or _fingerprint(parent.stat())[:3] != parent_identity:
                raise ValueError("Destination parent changed during generation")
            publish_noreplace(stage, destination)
            stage = None
        finally:
            if stage is not None:
                shutil.rmtree(stage)
        logging.info("Created paired fixture: %s", destination)
        return destination


def create_argparser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("runfolder", help="BFQ-style metadata and flat paired FASTQ source")
    parser.add_argument("--output", help="new output directory; existing parent required")
    parser.add_argument("--n-reads", default=1000, type=int, help="maximum pairs per sample / reads per mate file")
    parser.add_argument("--n-samples", default=3, type=int, help="legacy argument; explicit --samples is required")
    parser.add_argument("--samples", help="comma-separated exact sample IDs, without whitespace normalization")
    parser.add_argument("--no-fastq-rename", action="store_true", help="required: preserve flat BFQ filenames")
    parser.add_argument("--libprep-config", help="required explicit local libprep configuration")
    parser.add_argument("--project-id", help="required exact project ID")
    parser.add_argument("--seed", default=123456, type=int, help="paired reservoir seed")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None):
    parser = create_argparser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        source = BFQoutput(args.runfolder, libprep_config=args.libprep_config, project_id=args.project_id)
        source.sample(args.output, n_reads=args.n_reads, n_samples=args.n_samples,
                      samples=args.samples, no_fastq_rename=args.no_fastq_rename, seed=args.seed)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, "Testdata producer failed: {}\n".format(error))


if __name__ == "__main__":
    main()
