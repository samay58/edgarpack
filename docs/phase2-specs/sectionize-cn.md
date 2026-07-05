# Packet: sectionize-cn

Goal: stop the Chinese sectionizer from minting TOC entries as sections and from collapsing non-节 filings into one blob.

Files owned: `edgarpack/sse/sectionize_cn.py`, `edgarpack/config.py` (the PARSER_VERSION line only), tests (`tests/test_sectionize_cn.py`).

## Pre-made design decision: bump PARSER_VERSION

These changes alter SSE pack section bytes, and determinism is keyed on `PARSER_VERSION` (`edgarpack/config.py:50`). Verified before this spec was written: committed China fixture manifests carry no `parser_version` field, and no test compares a committed fixture manifest against the current constant (`tests/test_pack_doctor.py` constructs its own manifests from the constant). So: bump `PARSER_VERSION` from "0.2.1" to "0.2.2" as part of this packet, note the reason in the commit body, and do not regenerate any committed HK fixture sections (their source PDFs are untracked; they are unaffected).

## Fixes

1. `toc-guard`. `_SECTION_PATTERN` (~77-80) matches `第X节` at line start anywhere, so TOC entries with dot leaders (`第一节 释义 ...... 5`) become section boundaries: the TOC fragment steals the clean section id and the real section gets `_1`. Drop matches whose line remainder ends in dot/leader characters (`.`, `…`, `·`) plus optional whitespace and a page number. Regression test: a document with a full 10-entry dot-leader TOC followed by the real sections produces exactly the real sections with clean ids.

2. `zhang-support`. Filers using `第X章` or `第X部分` headings currently collapse to a single `unknown_01` section (~184-194). Support both families with the same numeral parsing and the same TOC guard. Regression test: a `第X章` document sectionizes.

3. `numerals`. The numeral table caps around 二十X; `_cn_num_to_int` (~89-104) returns 0 for 三十 and beyond. Extend compound handling to at least 九十九 (pattern: [tens-digit]十[units-digit]). Unit-test 三十, 三十五, 九十九, and the existing values.

## Done definition

New tests plus all existing sectionize tests green (existing synthetic fixtures may gain the realistic TOC block); PARSER_VERSION bumped with rationale in the commit body; full offline suite green.
