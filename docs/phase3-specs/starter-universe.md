# Packet: starter-universe

Goal: a curated ~50-name China universe an American investor would actually recognize, every identifier verified, loading cleanly through the dual-listing schema. This is the coverage seed and the future sweep corpus.

BASE BRANCH EXCEPTION: branch from `phase3/dual-listing-adr` (not the phase base): `git checkout -b phase3/starter-universe phase3/dual-listing-adr`. You need its loader semantics and pilot entries.

Files owned: `universe.toml` (China entries only; do not touch SEC-only entries), one loader-validation test file.

## The list

Candidate set below, authored from memory: VERIFICATION IS THE PACKET. Confirm every code/CIK against a live source (HKEX search, CNINFO, SEC ticker map) before committing; correct anything wrong and note corrections in the commit body. Skip a name only if verification fails outright (note it in the report). Dual-listed names get ONE entry with multiple identifiers per the dual-listing-adr schema; Alibaba/JD/BYD already exist from that packet.

US-listed (SEC 20-F, ADR ticker; add HK code where secondary-listed): NetEase (NTES, 9999.HK), Baidu (BIDU, 9888.HK), PDD Holdings (PDD), Bilibili (BILI, 9626.HK), Li Auto (LI, 2015.HK), NIO (NIO, 9866.HK), XPeng (XPEV, 9868.HK), Yum China (YUMC, 9987.HK), Trip.com (TCOM, 9961.HK), ZTO Express (ZTO, 2057.HK), Full Truck Alliance (YMM), KE Holdings (BEKE, 2423.HK), Vipshop (VIPS), Weibo (WB, 9898.HK), iQIYI (IQ), TAL Education (TAL), New Oriental (EDU, 9901.HK), Zai Lab (ZLAB, 9688.HK).

HKEX-primary: Tencent 00700 (already present), Meituan 03690 (present), Xiaomi 01810, Kuaishou 01024, Anta Sports 02020, Haidilao 06862, SenseTime 00020, China Mobile 00941 (also A 600941), AIA 01299, HSBC 00005, BYD Electronic 00285, Geely 00175, Great Wall Motor 02333 (also A 601633), Ping An 02318 (also A 601318), ICBC 01398 (also A 601398), CCB 00939 (also A 601939), CNOOC 00883 (also A 600938).

A-share-primary: Kweichow Moutai 600519, CATL 300750 (also H 3750.HK), Wuliangye 000858, Midea 000333 (also H 0300.HK), Gree 000651, Hikvision 002415, SMIC 688981 (also H 00981), Longi 601012, Muyuan 002714, East Money 300059, Hengrui 600276 (also H 1276.HK), Zijin Mining 601899 (also H 02899), Yili 600887, China Tourism Duty Free 601888 (also H 01880), Kingsoft Office 688111, Hygon 688041, Inovance 300124, Seres 601127, Yangtze Power 600900, BOE 000725, Foxconn Industrial Internet 601138, Sany Heavy 600031, WuXi AppTec 603259 (also H 02359).

## Entry conventions

- `aliases`: lowercase English name variants an American would type (e.g. "moutai", "kweichow moutai"); include the pinyin/company form already used by existing entries. No tickers in aliases (they go in alt_tickers).
- Dual-listed: `listing` = the venue with the richest English filings (SEC if a 20-F filer, else HKEX, else SSE).
- Keep formatting consistent with existing blocks; alphabetical is not required, grouping by venue is fine.

## Tests

One validation test that iterates every universe China entry and asserts: identifiers are well-formed (6-digit A-codes with known prefixes, 5-digit zero-padded HK codes, numeric CIKs), no duplicate identifiers across entries, every entry resolves through `identity.resolve` by its ticker and by at least one alias, and dual-listed entries carry a valid default `listing` for a populated identifier.

## Done definition

~45+ entries landed and verified (sources in commit body), validation test green, full offline suite green, `edgarpack identify moutai` and `identify BYDDY` resolve (assert in tests via the loader, not subprocess).
