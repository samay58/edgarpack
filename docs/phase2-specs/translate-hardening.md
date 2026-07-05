# Packet: translate-hardening

Goal: move the translation orchestrator out of the CLI god-file, bound its spend, and stop trusting truncated or empty provider responses.

Files owned: `edgarpack/china/translate/` (new `pipeline.py`, `deepinfra.py`, `__init__.py` exports), `edgarpack/cli.py` (the `_cmd_translate_sse` body ~1888-2290 and its argparse flags only), tests (`tests/test_translate_sse_artifacts.py`, `tests/test_deepinfra_translator.py`, new modules fine).
Note on cli.py: other packets edit other regions of cli.py; touch nothing outside the translate command body and its parser block.

## Fixes

1. `extract-pipeline`. `_cmd_translate_sse` is a ~400-line inline orchestrator (validation, retry, fail-closed section handling, manifest writes) with an `import json` at ~1899 shadowing the module-level import. Extract the orchestration into `edgarpack/china/translate/pipeline.py`; the CLI command becomes a thin wrapper (parse args, call pipeline, print summary). Behavior-preserving refactor: resume-by-default, failed section deletes its `.en.md` and blocks `filing.full.en.md`, `translation.failures.json` shape, manifest translation block, cache keying. This move is already scoped in `docs/BACKLOG.md` ("cli.py decomposition"), and `tests/test_translate_sse_artifacts.py` pins the behavior: it must pass unmodified (or with import-path-only changes, which you must call out in the report).

2. `spend-budget`. Worst case today is ~18 API attempts per paragraph with no ceiling. Add `--budget-tokens N` (0/absent = unlimited): accumulate prompt+completion token usage from DeepInfra responses; when the budget is crossed, finish the in-flight paragraph batch, persist consistent resume state (the same failed/pending bookkeeping resume already uses), and exit cleanly with a summary line stating tokens spent and where to resume. Budget exhaustion is a normal, non-zero-message exit, not a traceback.

3. `finish-reason`. `deepinfra.py`: a response with `finish_reason == "length"` is truncated output currently returned as-is (validators backstop it by burning the call), and empty `choices` echoes the input text back as the "translation". Treat `length` as a failed attempt (retry with the existing smaller-chunk/strict ladder, else fail the paragraph), and empty choices as a provider error, never input-echo-as-translation. Unit tests with mocked responses for both.

## Done definition

Pipeline extracted with `test_translate_sse_artifacts.py` green; `import json` shadowing gone; budget flag and finish-reason tests green; full offline suite green.
