"""Tests for etl/extract.py using a tiny synthetic mongodump archive (no network, no real data)."""
import gzip
import json
import struct
import zipfile
import zlib
from collections import Counter

import bson
import duckdb
import pytest

from etl import extract

MAGIC = b"\x6d\xe2\x99\x81"


def segment(collection, docs, eof=False):
    out = bson.encode({"db": "JiraReposAnon", "collection": collection, "EOF": eof, "CRC": 0})
    for d in docs:
        out += bson.encode(d)
    return out + struct.pack("<i", -1)


def archive(segments, collections=("Apache", "Other")):
    out = MAGIC + bson.encode({"concurrent_collections": 4, "server_version": "7.0.14"})
    for c in collections:
        out += bson.encode({"db": "JiraReposAnon", "collection": c, "metadata": "{}", "size": 0, "type": "collection"})
    return out + struct.pack("<i", -1) + b"".join(segments)


FULL = {
    "id": "123", "key": "KAFKA-1", "expand": "x", "self": "x",
    "fields": {
        "project": {"key": "KAFKA", "name": "Kafka"}, "issuetype": {"name": "Bug", "subtask": False},
        "status": {"name": "Resolved", "statusCategory": {"key": "done"}}, "resolution": {"name": "Fixed"},
        "priority": {"name": "Major"}, "created": "2020-01-01T10:00:00.000+0000",
        "updated": "2020-02-01T10:00:00.000+0000", "resolutiondate": "2020-01-11T10:00:00.000+0000",
        "assignee": {"name": "<<|dev|uuid-1|>>"}, "reporter": {"name": "<<|rep|uuid-2|>>"},
        "components": [{"name": "core"}], "fixVersions": [{"name": "1.0"}], "labels": ["x"],
        "issuelinks": [{}, {}], "summary": "Broker stalls", "description": "Details here", "timeoriginalestimate": 3600,
        "comment": {"comments": [{"id": "9", "author": {"name": "<<|c|uuid-3|>>"}, "created": "2020-01-02T10:00:00.000+0000", "body": "hello"}]},
    },
    "changelog": {"total": 1, "histories": [{"id": "10", "created": "2020-01-11T10:00:00.000+0000",
        "author": {"name": "<<|dev|uuid-1|>>"}, "items": [
            {"field": "status", "fieldtype": "jira", "from": "1", "fromString": "Open", "to": "5", "toString": "Resolved"},
            {"field": "resolution", "fieldtype": "jira", "from": None, "fromString": None, "to": "1", "toString": "Fixed"}]}]},
}
MINIMAL = {"id": "124", "key": "KAFKA-2", "fields": {"summary": "Bare", "resolution": None, "assignee": None}}
OTHER = {"id": "1", "key": "OTHER-1", "fields": {"summary": "not wanted"}}


def pieces(data, n=7):
    return (data[i:i + n] for i in range(0, len(data), n))


def parse(tmp_path, segments, **kw):
    gz = gzip.compress(archive(segments))
    manifest = extract.extract_archive(extract.gunzip(pieces(gz)), tmp_path / "out", **kw)
    return manifest, tmp_path / "out"


def table(path, name):
    return duckdb.sql(f"select * from read_parquet('{path / (name + '.parquet')}')")


def test_keeps_only_the_wanted_collection_even_when_segments_interleave(tmp_path):
    segs = [segment("Other", [OTHER]), segment("Apache", [FULL]), segment("Other", [OTHER, OTHER]), segment("Apache", [MINIMAL]),
            segment("Apache", [], eof=True)]
    manifest, out = parse(tmp_path, segs)
    assert manifest["tickets_written"] == 2
    assert manifest["documents_seen_by_collection"] == {"Other": 3, "Apache": 2}
    assert [r[0] for r in table(out, "issues").order("issue_key").fetchall()] == ["KAFKA-1", "KAFKA-2"]


def test_flattens_a_full_ticket(tmp_path):
    manifest, out = parse(tmp_path, [segment("Apache", [FULL])])
    row = table(out, "issues").fetchone()
    cols = [d[0] for d in table(out, "issues").description]
    t = dict(zip(cols, row))
    assert (t["issue_key"], t["project_key"], t["issue_type"], t["status"], t["resolution"], t["priority"]) == \
        ("KAFKA-1", "KAFKA", "Bug", "Resolved", "Fixed", "Major")
    assert t["created"] == "2020-01-01T10:00:00.000+0000" and t["resolution_date"] == "2020-01-11T10:00:00.000+0000"
    assert t["assignee"] == "<<|dev|uuid-1|>>" and t["components"] == ["core"] and t["fix_versions"] == ["1.0"]
    assert (t["link_count"], t["comment_count"], t["original_estimate_s"], t["changelog_total"], t["changelog_loaded"]) == (2, 1, 3600, 1, 1)
    changes = table(out, "changelog").order("field").fetchall()
    assert len(changes) == 2 and {c[4] for c in changes} == {"status", "resolution"}
    assert table(out, "comments").fetchone()[5] == len("hello")  # body length kept, body dropped
    assert table(out, "issue_text").fetchone() == ("KAFKA-1", "Broker stalls", "Details here")
    assert manifest["changelog_fields"] == {"status": 1, "resolution": 1}


def test_missing_fields_become_nulls_not_errors(tmp_path):
    manifest, out = parse(tmp_path, [segment("Apache", [MINIMAL])])
    cols = [d[0] for d in table(out, "issues").description]
    t = dict(zip(cols, table(out, "issues").fetchone()))
    assert t["project_key"] == "KAFKA" and t["priority"] is None and t["assignee"] is None and t["comment_count"] == 0
    assert manifest["tickets_failed"] == 0


def test_limit_issues_stops_early_and_says_so(tmp_path):
    manifest, _ = parse(tmp_path, [segment("Apache", [FULL, MINIMAL, FULL])], limit_issues=2)
    assert manifest["tickets_written"] == 2 and manifest["complete_pass"] is False


def test_truncated_archive_is_an_error_not_silent(tmp_path):
    gz = gzip.compress(archive([segment("Apache", [FULL])]))
    cut = zlib.decompressobj(31).decompress(gz)[:-40]  # chop the end off the archive
    with pytest.raises(EOFError):
        extract.extract_archive(pieces(cut), tmp_path / "out")


def test_not_an_archive_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        extract.extract_archive(pieces(b"PK\x03\x04 definitely not it"), tmp_path / "out")


def test_zip_entry_is_checked_against_the_zip_directory():
    payload = gzip.compress(archive([segment("Apache", [FULL])]))
    c = zlib.compressobj(6, zlib.DEFLATED, -15)
    deflated = c.compress(payload) + c.flush()
    good = extract.Check(zlib.crc32(payload), len(payload))
    assert b"".join(extract.inflate_zip_entry(pieces(deflated), good)) == payload and good.verify()
    bad = extract.Check(zlib.crc32(payload) ^ 1, len(payload))
    b"".join(extract.inflate_zip_entry(pieces(deflated), bad))
    with pytest.raises(RuntimeError):
        bad.verify()


def test_end_to_end_from_a_local_zip(tmp_path):
    zpath = tmp_path / "ds.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("1. README.md", "hello")
        z.writestr("3. DataDump/mongodump-test.archive", gzip.compress(archive([segment("Apache", [FULL, MINIMAL])])))
    out = tmp_path / "raw" / "apache"
    manifest = extract.run(source=str(zpath), out=out)
    assert manifest["tickets_written"] == 2 and manifest["zip_entry_check"] == "passed"
    assert json.loads((out / "manifest.json").read_text())["tickets_written"] == 2
    again = extract.run(source=str(zpath), out=out)  # second run reuses the finished extraction
    assert again["tickets_written"] == 2


def test_parallel_download_is_in_order_and_survives_a_failing_segment():
    import http.server
    import threading

    data = bytes(range(256)) * 4000  # 1,024,000 bytes
    state = {"failed": False}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            lo, hi = self.headers["Range"].split("=")[1].split("-")
            lo, hi = int(lo), int(hi)
            if lo == 300_100 and not state["failed"]:
                state["failed"] = True
                self.send_response(500); self.end_headers(); return
            body = data[lo:hi + 1]
            self.send_response(206)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/f"
        got = b"".join(extract.parallel_chunks(url, 100, 1_000_000, connections=4, segment=50_000, retries=3))
    finally:
        server.shutdown()
    assert got == data[100:1_000_001] and state["failed"]
