# Public Jira Dataset: structure (fact-finding)

Source: Zenodo record 15719919 (published 2025-06-23), Montgomery, Lüders, Maalej, MSR 2022. License CC BY 4.0 (data), MIT (code).
Verified by HTTP range requests only; nothing large downloaded (about 4 MB of the archive head, 2 MB of the zip tail).

## Access
- File URL: https://zenodo.org/api/records/15719919/files/2025-06-23%20ThePublicJiraDataset.zip/content
- Zenodo honours Range on GET (HTTP 206). A HEAD with Range returns 200, so test with GET. Rate limit header: 133 requests per window.
- Size 5,813,135,238 bytes. ZIP64: EOCD says 27 entries, central directory at offset 5,813,131,370, 3,770 bytes.

## (1) Zip entries (compressed / uncompressed bytes; local offset)
| Entry (under ThePublicJiraDataset/) | comp | uncomp | offset |
|---|---|---|---|
| 0. DataDefinition/May2021/jira_data_sources_MAY_2021.json | 570 | 2,775 | 197 |
| 0. DataDefinition/May2021/jira_field_information_MAY_2021.json | 76,543 | 1,339,924 | 875 |
| 0. DataDefinition/May2021/jira_issuetype_information_MAY_2021.json | 16,037 | 197,686 | 77,531 |
| 0. DataDefinition/jira_data_sources.json | 574 | 2,778 | 93,685 |
| 0. DataDefinition/jira_field_information.json | 77,011 | 1,290,419 | 94,350 |
| 0. DataDefinition/jira_issue_linktype_mapping.json | 666 | 2,618 | 171,457 |
| 0. DataDefinition/jira_issuelinktype_information.json | 4,013 | 48,953 | 172,224 |
| 0. DataDefinition/jira_issuetype_information.json | 17,356 | 216,730 | 176,341 |
| 0. DataDefinition/jira_issuetype_thematic_analysis.json | 1,634 | 26,659 | 193,797 |
| 1. DataDownload/DownloadData.ipynb | 6,482 | 31,477 | 195,604 |
| 1. DataDownload/README.md | 337 | 658 | 202,171 |
| 1. DataDownload/requirements-manual.txt | 181 | 278 | 202,584 |
| 2. OverviewAnalysis/OverviewAnalysis.ipynb | 7,338 | 47,279 | 202,926 |
| 2. OverviewAnalysis/OverviewAnalysisResults.png | 262,048 | 296,735 | 210,357 |
| 2. OverviewAnalysis/README.md | 343 | 662 | 472,503 |
| 2. OverviewAnalysis/requirements-manual.txt | 199 | 313 | 472,926 |
| 3. DataDump/README.md | 297 | 600 | 473,282 |
| **3. DataDump/mongodump-JiraReposAnon.archive** | **5,812,650,045** | **5,865,360,994** | 473,651 |
| LICENSE-CCBY4.0.md | 4,984 | 17,067 | 5,813,123,810 |
| LICENSE-MIT.md | 620 | 1,073 | 5,813,128,863 |
| README.md | 1,762 | 4,313 | 5,813,129,548 |
(plus 6 directory entries.) All entries are deflate (method 8). The dump is one entry that is 99.99% of the zip.

## (2) Dump layout
- The single data file is a `mongodump --db=JiraReposAnon --gzip --archive=...` archive (server 7.0.14, tool 100.9.5). README says about 60 GB expanded inside MongoDB.
- Layering: zip deflate -> gzip stream (the whole archive is gzip-wrapped, magic 1f8b; deflate barely compresses it, ratio 0.99; so the 5.87 GB uncompressed zip entry is itself a .gz of the ~60 GB archive) -> mongodump archive format (magic bytes 6d e2 99 81, then BSON documents).
- Not a directory of per-collection .bson files; it is the interleaved archive format.
- Collections (verified from the archive prefix): exactly 16, one per Jira instance, named by instance: MongoDB, SecondLife, Hyperledger, Mindville, JiraEcosystem, Mojang, Apache, Sonatype, Spring, Jira, Qt, RedHat, JFrog, IntelDAOS, MariaDB, Sakai. **Apache is its own collection** (about 970,000 issues per jira_data_sources.json). Each collection holds only index `_id_`. Rough issue counts from jira_data_sources.json: Apache 970k, RedHat 315k, Mojang 375k, Jira 265k, Qt 140k, MongoDB 90k, Sonatype 78k, Spring 69k, Sakai 49k, JiraEcosystem 41k, MariaDB 30k, Hyperledger 28k, JFrog 15k, IntelDAOS 6k, Mindville 2k, SecondLife 2k.
- Archive stream order: header doc, 16 namespace metadata docs, 0xFFFFFFFF terminator, then chunks of `{db, collection, EOF, CRC}` header + documents + 0xFFFFFFFF terminator. With concurrent_collections=4, chunks from different collections are interleaved (first 44 MB showed Jira, RedHat, Mojang interleaved, about 1,000-1,300 docs per chunk). So Apache documents are scattered through the whole stream, not contiguous: extracting Apache means a sequential pass over all ~60 GB of uncompressed archive (5.8 GB compressed), filtering on the namespace header.

## (3) Issue document schema (one collection doc = one Jira REST v2 issue)
Top level: `_id` (ObjectId), `expand`, `id`, `self`, `key`, `fields`, `changelog`.
- `fields.created`, `fields.updated`, `fields.resolutiondate`: strings like "2022-01-04T09:13:21.000+0000" (resolutiondate null when unresolved)
- `fields.status`: object {self,description,iconUrl,name,id,statusCategory{id,key,name,colorName}}
- `fields.resolution`: null or object (name, id)
- `fields.priority`: object with name/id (not present in the Jira-instance sample I read, which is a Suggestion-type project; check per instance, field availability varies. jira_field_information.json lists fields per repo)
- `fields.issuetype`: {id,name,description,subtask,...}
- `fields.assignee`, `creator`, `reporter`: anonymised; strings of form `<<|author_name|<uuid4>|>>`, `<<|author_displayName|<uuid4>|>>`; assignee null if none
- `fields.project` {id,key,name,projectTypeKey,...}, `components`, `fixVersions`, `labels`, `issuelinks`, `subtasks`, `votes`, `watches`, `comments` (list; moved into fields), many `customfield_NNNNN`
- `changelog`: {startAt, maxResults, total, histories[]}. Each history is the standard Jira entry (author, created, items[{field,fromString,toString,...}]); sample issue had empty histories, so item field names not directly confirmed here but standard Jira REST v2 changelog.
- Sample (Jira collection, SRCTREEWIN-13759): created 2022-01-04, status "Gathering Interest" (category To Do), issuetype "Suggestion", resolution null, resolutiondate null, assignee null.
- Not yet checked: a sample from the Apache collection (priority, non-empty histories); would need a sequential read far into the stream.

## (4) Reading with plain Python
- Installed in repo `.venv`: duckdb yes; pymongo no; bson no. Nothing installed. (System python3 also lacks bson.)
- mongod is not needed. Streaming works: HTTP range GET of the zip entry from local-header offset 473,651 (header 30 + 64 name + 20 extra = data starts at 474,... i.e. offset + 114), `zlib.decompressobj(-15)` for the zip deflate, then `zlib.decompressobj(31)` (or `gzip`) for the mongodump gzip, then parse the archive. I did this for the first 4 MB (-> 43.8 MB archive prefix) successfully, with a ~60-line hand-written BSON decoder.
- Streaming one pass of the whole thing is the only way to reach later chunks: the stream is sequential deflate+gzip with no seek index, so you cannot jump to Apache. Cost: download 5.8 GB (can be piped, not stored) and decompress ~60 GB, discarding non-Apache chunks; wall time dominated by network+inflate. Disk use stays small if piped.
- Parsing: either `pip install pymongo` then `bson.decode_file_iter` / `bson.decode_all` on each length-prefixed doc (BSON docs are int32-length-prefixed; archive framing, namespace headers and 0xFFFFFFFF terminators must be handled by you: read int32, if -1 end of chunk, if doc has keys db+collection+EOF it is a chunk header), or the simple decoder pattern above (types needed: double, string, doc, array, binary, objectid, bool, datetime, null, int32, int64). No mongorestore needed. Alternatively `mongorestore` into mongod needs ~60 GB disk: not feasible here.
- Practical implication for a ~12 GB disk: pipe-stream, filter to Apache (or a subset of fields: key, created, resolutiondate, status, resolution, priority, issuetype, assignee, project, changelog histories), write compact Parquet/CSV (duckdb is available). Possible early stop is not feasible if Apache is wanted completely.
