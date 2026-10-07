"""Extract the Apache issues from The Public Jira Dataset into slim Parquet files.

The dataset (Montgomery et al., CC BY 4.0, Zenodo record 15719919) ships as one zip whose
main entry is a `mongodump --gzip --archive` of 16 Jira instances (about 60 GB expanded).
Restoring it needs MongoDB and far more disk than this project has, so this script streams it:

    parallel HTTP range requests -> zip deflate -> gzip -> mongodump archive framing -> BSON documents

Only documents from the wanted collection (Apache) are decoded; everything else is skipped
unread. Nothing large is written to disk. Output goes to `data/raw/apache_jira/`:

    issues.parquet      one row per ticket: attributes, dates, people (anonymised), counts
    changelog.parquet   one row per changelog item (field changes, including status)
    comments.parquet    one row per comment, without the body
    issue_text.parquet  ticket title and description, kept apart so it is optional
    manifest.json       source, integrity checks, counts and field-presence statistics

Dates are kept as the dataset's own strings; `etl/load.py` types them in DuckDB.

Run from the repo root:  python -m etl.extract            (full pass, long)
                         python -m etl.extract --limit-issues 2000 --out data/raw/apache_jira_probe
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import struct
import sys
import time
import zipfile
import zlib
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import bson
import pyarrow as pa
import pyarrow.parquet as pq
import requests

ZENODO_URL = "https://zenodo.org/api/records/15719919/files/2025-06-23%20ThePublicJiraDataset.zip/content"
ZENODO_RECORD = "https://zenodo.org/records/15719919"
ZIP_MD5 = "02f85309d966092ea130ca0797aea795"  # of the whole zip, per the Zenodo record
ENTRY_SUFFIX = ".archive"
ARCHIVE_MAGIC = b"\x6d\xe2\x99\x81"
DEFAULT_OUT = Path("data/raw/apache_jira")
CHUNK = 1 << 20

ISSUES_SCHEMA = pa.schema([
    ("issue_key", pa.string()), ("issue_id", pa.string()), ("project_key", pa.string()),
    ("project_name", pa.string()), ("issue_type", pa.string()), ("is_subtask", pa.bool_()),
    ("status", pa.string()), ("status_category", pa.string()), ("resolution", pa.string()),
    ("priority", pa.string()), ("created", pa.string()), ("updated", pa.string()),
    ("resolution_date", pa.string()), ("due_date", pa.string()),
    ("assignee", pa.string()), ("reporter", pa.string()), ("creator", pa.string()),
    ("components", pa.list_(pa.string())), ("fix_versions", pa.list_(pa.string())),
    ("labels", pa.list_(pa.string())), ("link_count", pa.int32()), ("comment_count", pa.int32()),
    ("original_estimate_s", pa.int64()), ("time_spent_s", pa.int64()),
    ("changelog_total", pa.int32()), ("changelog_loaded", pa.int32()),
])
CHANGELOG_SCHEMA = pa.schema([
    ("issue_key", pa.string()), ("history_id", pa.string()), ("created", pa.string()),
    ("author", pa.string()), ("field", pa.string()), ("field_type", pa.string()),
    ("from_value", pa.string()), ("from_string", pa.string()),
    ("to_value", pa.string()), ("to_string", pa.string()),
])
COMMENTS_SCHEMA = pa.schema([
    ("issue_key", pa.string()), ("comment_id", pa.string()), ("created", pa.string()),
    ("updated", pa.string()), ("author", pa.string()), ("body_length", pa.int32()),
])
TEXT_SCHEMA = pa.schema([
    ("issue_key", pa.string()), ("summary", pa.string()), ("description", pa.string()),
])


# ----------------------------------------------------------------------------- reading the source

class RangeFile(io.RawIOBase):
    """A seekable read-only file over an HTTP URL, using range requests (for the zip directory)."""

    def __init__(self, url: str, session: requests.Session):
        self.url, self.session, self.pos = url, session, 0
        r = session.get(url, headers={"Range": "bytes=0-0"}, timeout=(30, 60))
        if r.status_code != 206:
            raise RuntimeError(f"server does not honour range requests (HTTP {r.status_code})")
        self.size = int(r.headers["Content-Range"].rsplit("/", 1)[1])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        r = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}"}, timeout=(30, 120))
        r.raise_for_status()
        b[:len(r.content)] = r.content
        self.pos += len(r.content)
        return len(r.content)


def http_chunks(session, url, start, end, retries=12):
    """Yield bytes [start, end] in order. On a dropped connection, resume from the exact byte."""
    pos, attempt = start, 0
    while pos <= end:
        try:
            with session.get(url, headers={"Range": f"bytes={pos}-{end}"}, stream=True, timeout=(30, 120)) as r:
                if r.status_code != 206:
                    raise requests.RequestException(f"HTTP {r.status_code}")
                for chunk in r.iter_content(CHUNK):
                    pos += len(chunk)
                    attempt = 0
                    yield chunk
        except (requests.RequestException, OSError) as exc:
            attempt += 1
            if attempt > retries:
                raise
            wait = min(60, 2 ** attempt)
            print(f"\n[extract] connection problem at byte {pos} ({exc!r}); retry {attempt}/{retries} in {wait}s", file=sys.stderr)
            time.sleep(wait)


def parallel_chunks(url, start, end, connections=16, segment=16 << 20, retries=8):
    """Yield bytes [start, end] in order, fetching several segments at once.

    Zenodo caps the speed of each connection, so one stream is slow. Segments are downloaded
    concurrently but handed on strictly in order; at most 2 x connections segments are held in memory.
    """
    def fetch(lo, hi):
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, headers={"Range": f"bytes={lo}-{hi}"}, timeout=(30, 120))
                if r.status_code != 206 or len(r.content) != hi - lo + 1:
                    raise requests.RequestException(f"HTTP {r.status_code}, {len(r.content)} bytes for {hi - lo + 1}")
                return r.content
            except (requests.RequestException, OSError) as exc:
                if attempt == retries:
                    raise
                wait = min(60, 2 ** (attempt + 1))
                print(f"\n[extract] segment at byte {lo} failed ({exc!r}); retry {attempt + 1}/{retries} in {wait}s", file=sys.stderr)
                time.sleep(wait)

    spans = iter([(lo, min(lo + segment - 1, end)) for lo in range(start, end + 1, segment)])
    pool, pending = ThreadPoolExecutor(connections), deque()
    try:
        def top_up():
            while len(pending) < connections * 2:
                span = next(spans, None)
                if span is None:
                    return
                pending.append(pool.submit(fetch, *span))
        top_up()
        while pending:
            data = pending.popleft().result()
            top_up()
            yield data
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def file_chunks(path, start, end):
    with open(path, "rb") as f:
        f.seek(start)
        left = end - start + 1
        while left > 0:
            data = f.read(min(CHUNK, left))
            if not data:
                raise EOFError("local file ended early")
            left -= len(data)
            yield data


class Check:
    """Holds the zip entry's expected CRC and size, filled in as the stream is inflated."""
    def __init__(self, crc, size):
        self.expected_crc, self.expected_size, self.crc, self.size, self.done = crc, size, 0, 0, False

    def verify(self):
        if self.size != self.expected_size or self.crc != self.expected_crc:
            raise RuntimeError(f"zip entry check failed: size {self.size}/{self.expected_size}, crc {self.crc:08x}/{self.expected_crc:08x}")
        return True


def inflate_zip_entry(chunks, check: Check):
    """Raw deflate (zip method 8) -> bytes, updating the CRC32 the zip directory promises."""
    d = zlib.decompressobj(-15)
    for chunk in chunks:
        out = d.decompress(chunk)
        if out:
            check.crc, check.size = zlib.crc32(out, check.crc), check.size + len(out)
            yield out
    out = d.flush()
    if out:
        check.crc, check.size = zlib.crc32(out, check.crc), check.size + len(out)
        yield out
    check.done = True


def gunzip(chunks):
    """Gzip -> bytes. Handles concatenated members; zlib itself verifies each member's CRC."""
    d = zlib.decompressobj(31)
    for chunk in chunks:
        while chunk:
            out = d.decompress(chunk)
            if out:
                yield out
            if d.eof:
                chunk, d = d.unused_data, zlib.decompressobj(31)
            else:
                chunk = b""


class ByteStream:
    """Incremental reader over a generator of byte chunks."""

    def __init__(self, chunks):
        self.it, self.buf, self.pos, self.consumed = iter(chunks), bytearray(), 0, 0

    def _fill(self, n):
        while len(self.buf) - self.pos < n:
            try:
                chunk = next(self.it)
            except StopIteration:
                return False
            if self.pos > (4 << 20):
                del self.buf[:self.pos]
                self.pos = 0
            self.buf += chunk
        return True

    def read(self, n):
        if not self._fill(n):
            raise EOFError("archive ended in the middle of a record")
        out = bytes(self.buf[self.pos:self.pos + n])
        self.pos += n
        self.consumed += n
        return out

    def read_int32(self, allow_eof=False):
        if not self._fill(4):
            if allow_eof and len(self.buf) == self.pos:
                return None
            raise EOFError("archive ended in the middle of a length prefix")
        value = struct.unpack_from("<i", self.buf, self.pos)[0]
        self.pos += 4
        self.consumed += 4
        return value

    def skip(self, n):
        self.consumed += n
        while n:
            avail = len(self.buf) - self.pos
            if not avail:
                if not self._fill(1):
                    raise EOFError("archive ended while skipping a document")
                continue
            take = min(avail, n)
            self.pos += take
            n -= take


# ----------------------------------------------------------------------------- the mongodump archive

def read_doc(stream, length):
    return bson.decode(struct.pack("<i", length) + stream.read(length - 4))


def iter_archive(stream: ByteStream, wanted: str, counts: Counter, namespaces: list):
    """Yield documents of the wanted collection. Documents of other collections are skipped unread.

    Format: magic, header doc, namespace metadata docs, 0xFFFFFFFF, then segments of
    [ {db, collection, EOF, CRC} header, documents..., 0xFFFFFFFF ], interleaved across collections.
    """
    if stream.read(4) != ARCHIVE_MAGIC:
        raise ValueError("not a mongodump archive (bad magic bytes)")
    read_doc(stream, stream.read_int32())  # archive header
    while True:  # namespace metadata until the terminator
        length = stream.read_int32()
        if length == -1:
            break
        meta = read_doc(stream, length)
        namespaces.append(f"{meta.get('db')}.{meta.get('collection')}")
    current = None
    while True:
        length = stream.read_int32(allow_eof=True)
        if length is None:
            return
        if length == -1:
            current = None
            continue
        if current is None:  # segment header
            header = read_doc(stream, length)
            current = header.get("collection")
            continue
        counts[current] += 1
        if current == wanted:
            yield read_doc(stream, length)
        else:
            stream.skip(length - 4)


# ----------------------------------------------------------------------------- flattening one ticket

def text(x):
    return x if isinstance(x, str) else None


def named(x):
    return text(x.get("name")) if isinstance(x, dict) else text(x)


def person(x):
    """People are anonymised in this dataset; take whatever stable identifier the field carries."""
    if isinstance(x, dict):
        for k in ("key", "name", "accountId", "displayName", "emailAddress"):
            if text(x.get(k)):
                return x[k]
        return None
    return text(x)


def names(xs):
    return [n for n in (named(x) for x in xs) if n] if isinstance(xs, list) else []


def integer(x):
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def flatten(doc, stats: Counter):
    """One Jira REST v2 issue -> (issue row, changelog rows, comment rows, text row)."""
    f = doc.get("fields") or {}
    key = text(doc.get("key"))
    project = f.get("project") if isinstance(f.get("project"), dict) else {}
    issuetype = f.get("issuetype") if isinstance(f.get("issuetype"), dict) else {}
    status = f.get("status") if isinstance(f.get("status"), dict) else {}
    category = status.get("statusCategory") if isinstance(status.get("statusCategory"), dict) else {}
    comments_field = f.get("comment", f.get("comments"))
    comments = comments_field.get("comments", []) if isinstance(comments_field, dict) else (comments_field or [])
    comments = [c for c in comments if isinstance(c, dict)]
    log = doc.get("changelog") if isinstance(doc.get("changelog"), dict) else {}
    histories = [h for h in (log.get("histories") or []) if isinstance(h, dict)]

    change_rows = []
    for h in histories:
        for item in h.get("items") or []:
            stats["changelog_field:" + str(item.get("field"))] += 1
            change_rows.append({
                "issue_key": key, "history_id": text(str(h.get("id")) if h.get("id") is not None else None),
                "created": text(h.get("created")), "author": person(h.get("author")),
                "field": text(item.get("field")), "field_type": text(item.get("fieldtype")),
                "from_value": text(item.get("from")), "from_string": text(item.get("fromString")),
                "to_value": text(item.get("to")), "to_string": text(item.get("toString")),
            })
    comment_rows = [{
        "issue_key": key, "comment_id": text(str(c.get("id")) if c.get("id") is not None else None),
        "created": text(c.get("created")), "updated": text(c.get("updated")),
        "author": person(c.get("author")), "body_length": len(c.get("body") or "") if isinstance(c.get("body"), str) else None,
    } for c in comments]

    issue = {
        "issue_key": key, "issue_id": text(str(doc.get("id")) if doc.get("id") is not None else None),
        "project_key": text(project.get("key")) or (key.rsplit("-", 1)[0] if key and "-" in key else None),
        "project_name": text(project.get("name")), "issue_type": named(issuetype),
        "is_subtask": issuetype.get("subtask") if isinstance(issuetype.get("subtask"), bool) else None,
        "status": named(status), "status_category": text(category.get("key")) or text(category.get("name")),
        "resolution": named(f.get("resolution")), "priority": named(f.get("priority")),
        "created": text(f.get("created")), "updated": text(f.get("updated")),
        "resolution_date": text(f.get("resolutiondate")), "due_date": text(f.get("duedate")),
        "assignee": person(f.get("assignee")), "reporter": person(f.get("reporter")), "creator": person(f.get("creator")),
        "components": names(f.get("components")), "fix_versions": names(f.get("fixVersions")),
        "labels": [x for x in (f.get("labels") or []) if isinstance(x, str)] if isinstance(f.get("labels"), list) else [],
        "link_count": len(f.get("issuelinks") or []) if isinstance(f.get("issuelinks"), list) else None,
        "comment_count": len(comments), "original_estimate_s": integer(f.get("timeoriginalestimate")),
        "time_spent_s": integer(f.get("timespent")), "changelog_total": integer(log.get("total")),
        "changelog_loaded": len(histories),
    }
    for col in ("priority", "resolution", "assignee", "resolution_date", "due_date", "status_category"):
        stats["present:" + col] += issue[col] is not None
    stats["changelog_truncated"] += (issue["changelog_total"] is not None and issue["changelog_total"] != len(histories))
    text_row = {"issue_key": key, "summary": text(f.get("summary")), "description": text(f.get("description"))}
    return issue, change_rows, comment_rows, text_row


class ParquetOut:
    def __init__(self, path, schema, batch):
        self.writer, self.schema, self.batch, self.rows, self.written = pq.ParquetWriter(path, schema, compression="zstd"), schema, batch, [], 0

    def add(self, items):
        self.rows.extend(items)
        if len(self.rows) >= self.batch:
            self.flush()

    def flush(self):
        if self.rows:
            self.writer.write_table(pa.Table.from_pylist(self.rows, schema=self.schema))
            self.written += len(self.rows)
            self.rows = []

    def close(self):
        self.flush()
        self.writer.close()


def extract_archive(archive_chunks, out_dir: Path, collection="Apache", limit_issues=None, log=None):
    """Parse an (already gunzipped) mongodump archive and write the Parquet files into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = {
        "issues": ParquetOut(out_dir / "issues.parquet", ISSUES_SCHEMA, 20_000),
        "changelog": ParquetOut(out_dir / "changelog.parquet", CHANGELOG_SCHEMA, 400_000),
        "comments": ParquetOut(out_dir / "comments.parquet", COMMENTS_SCHEMA, 200_000),
        "issue_text": ParquetOut(out_dir / "issue_text.parquet", TEXT_SCHEMA, 5_000),
    }
    stream, seen, namespaces, stats = ByteStream(archive_chunks), Counter(), [], Counter()
    errors, error_samples, kept, started, last_log = 0, [], 0, time.time(), 0.0
    complete = True
    try:
        for doc in iter_archive(stream, collection, seen, namespaces):
            try:
                issue, changes, comments, text_row = flatten(doc, stats)
            except Exception as exc:  # keep going; report in the manifest
                errors += 1
                if len(error_samples) < 5:
                    error_samples.append({"key": str(doc.get("key")), "error": repr(exc)})
                continue
            outs["issues"].add([issue]); outs["changelog"].add(changes)
            outs["comments"].add(comments); outs["issue_text"].add([text_row])
            kept += 1
            if limit_issues and kept >= limit_issues:
                complete = False
                break
            if log and time.time() - last_log > 15:
                last_log = time.time()
                log(stream.consumed, kept, seen)
    finally:
        for o in outs.values():
            o.close()
    return {
        "collection": collection, "complete_pass": complete, "limit_issues": limit_issues,
        "namespaces_in_archive": namespaces, "documents_seen_by_collection": dict(seen),
        "tickets_written": outs["issues"].written, "changelog_items_written": outs["changelog"].written,
        "comments_written": outs["comments"].written, "tickets_failed": errors, "failure_samples": error_samples,
        "archive_bytes_read": stream.consumed, "seconds": round(time.time() - started, 1),
        "field_presence": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("present:")},
        "changelog_fields": {k.split(":", 1)[1]: v for k, v in stats.most_common() if k.startswith("changelog_field:")},
        "tickets_with_truncated_changelog": stats["changelog_truncated"],
    }


# ----------------------------------------------------------------------------- the whole pipeline

def open_source(source: str, connections: int = 16):
    """Return (name, header_offset, compressed_size, crc, size, chunk_factory) for the dump entry."""
    if Path(source).exists():
        zf = zipfile.ZipFile(source)
        factory = lambda start, end: file_chunks(source, start, end)
        raw = open(source, "rb")
    else:
        session = requests.Session()
        raw = io.BufferedReader(RangeFile(source, session), 1 << 16)
        zf = zipfile.ZipFile(raw)
        factory = (lambda start, end: parallel_chunks(source, start, end, connections)) if connections > 1 \
            else (lambda start, end: http_chunks(session, source, start, end))
    infos = [i for i in zf.infolist() if i.filename.endswith(ENTRY_SUFFIX)]
    if len(infos) != 1:
        raise RuntimeError(f"expected one {ENTRY_SUFFIX} entry in the zip, found {[i.filename for i in zf.infolist()]}")
    info = infos[0]
    if info.compress_type != zipfile.ZIP_DEFLATED:
        raise RuntimeError(f"unexpected zip compression method {info.compress_type}")
    raw.seek(info.header_offset)
    header = raw.read(30)
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    start = info.header_offset + 30 + name_len + extra_len
    return info, start, factory


def run(source=ZENODO_URL, out=DEFAULT_OUT, collection="Apache", limit_issues=None, force=False, connections=16):
    out = Path(out)
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and not force:
        done = json.loads(manifest_path.read_text())
        if done.get("complete_pass") and not limit_issues:
            print(f"[extract] {out} already holds a complete extraction ({done['tickets_written']:,} tickets). Use --force to redo.")
            return done
    partial = out.parent / (out.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    print(f"[extract] reading the zip directory from {source}")
    info, start, factory = open_source(source, connections)
    end = start + info.compress_size - 1
    print(f"[extract] entry '{info.filename}': {info.compress_size / 1e9:.2f} GB compressed, {info.file_size / 1e9:.2f} GB as gzip")
    check = Check(info.CRC, info.file_size)
    archive = gunzip(inflate_zip_entry(factory(start, end), check))
    started = time.time()

    def log(consumed, kept, seen):
        rate = consumed / max(time.time() - started, 1) / 1e6
        print(f"\r[extract] {consumed / 1e9:6.1f} GB of archive read ({rate:5.0f} MB/s) | {collection} tickets kept: {kept:,} | "
              f"documents seen: {sum(seen.values()):,}", end="", file=sys.stderr, flush=True)

    manifest = extract_archive(archive, partial, collection, limit_issues, log)
    print(file=sys.stderr)
    manifest["zip_entry_check"] = "skipped (stopped early)" if not manifest["complete_pass"] else (check.verify() and "passed")
    manifest.update({
        "source": source if not Path(source).exists() else str(source), "zenodo_record": ZENODO_RECORD,
        "license": "CC BY 4.0", "whole_zip_md5_per_zenodo": ZIP_MD5, "zip_entry": info.filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    (partial / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if out.exists():
        shutil.rmtree(out)
    partial.rename(out)
    print(f"[extract] wrote {manifest['tickets_written']:,} tickets, {manifest['changelog_items_written']:,} changelog items, "
          f"{manifest['comments_written']:,} comments to {out}")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", default=ZENODO_URL, help="URL or local path of the dataset zip")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--collection", default="Apache", help="which Jira instance to keep")
    p.add_argument("--limit-issues", type=int, default=None, help="stop after N tickets (probe run)")
    p.add_argument("--force", action="store_true", help="redo even if a complete extraction exists")
    p.add_argument("--connections", type=int, default=16, help="parallel download connections (1 = a single stream)")
    a = p.parse_args(argv)
    run(a.source, a.out, a.collection, a.limit_issues, a.force, a.connections)


if __name__ == "__main__":
    main()
