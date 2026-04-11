---
name: learn-pack
description: Generate a deep, narrative learning pack (docs/learn/) for a codebase. Two-phase workflow — discovery + plan, then fill one piece at a time. Used when a developer or agent needs to truly understand a system, not just read its API. Trails tell stories; refs are the dictionary.
---

# learn-pack

Generate `docs/learn/` for the host repo. You are the writer. This file is the playbook.

> **Hard rule**: read `PRINCIPLES.md` (next to this file) before writing a single line of prose. The principles are the difference between a learn pack and AI slop.

## What you produce

A `docs/learn/` directory in the host repo containing:

- `README.md` — index, napkin sketch, links into the trails and refs
- `manifest.yml` — the plan you wrote in Phase 1 (kept around so future runs can update incrementally)
- `trail-N-<slug>.md` — narrative walks through concrete actions ("you run X, here's what happens")
- `ref/ref-<module>.md` — function-level reference docs for the modules that matter

The exact count and shape come from discovery. Don't pre-decide. Marginalia's learn pack has 4 trails and 3 refs because that fit marginalia. Edgarpack might have 6 trails and 8 refs. Let the codebase decide.

## The two phases

### Phase 1 — Discovery + Plan

Goal: produce `docs/learn/manifest.yml` and stop. **You do not write trails or refs in Phase 1.**

Steps:

1. **Read what's already there.** README.md, ARCHITECTURE.md, AGENTS.md, CLAUDE.md, any docs/ tree, any pyproject.toml / package.json. These tell you what the maintainers think the system is. You will treat them as input, not gospel.
2. **Walk the source tree.** Identify entry points (CLIs, public modules, HTTP handlers, main functions). Identify the natural lifecycle of the system — the order data flows through it. Most systems have one or two dominant lifecycles. Find them.
3. **Read 5-10 key files end-to-end.** Not skim — read. Pick the entry point and follow the call chain. If you can't trace what happens when a user runs the most common command, you're not ready to plan.
4. **Draft the napkin sketch.** A short ascii diagram (8-12 lines) of the dominant lifecycle, in plain English verbs. This goes in `manifest.yml` and later in `README.md`. If you can't draw it, you don't understand the system yet — go back to step 3.
5. **Plan trails.** Each trail is a story rooted in a concrete action. "You run `edgarpack query NVDA revenue`, here's the chain." Pick trails that, taken together, hit every load-bearing module in the lifecycle. Estimate reading time honestly (8-20 min each).
6. **Plan refs.** A ref doc exists for each module that other modules depend on heavily, or that has subtle invariants worth documenting. Not every file needs a ref. If a module is just glue or a thin wrapper, link to it from a trail and skip the ref.
7. **Write `docs/learn/manifest.yml`** using `templates/manifest.yml.tmpl` as the structure. Include `omitted:` for anything you deliberately skipped, with a one-line reason.
8. **Stop.** Tell the user the manifest is ready and ask them to review it.

### Phase 2 — Fill

Once the user approves the manifest, work through it **one item at a time**, top to bottom.

For each trail:

1. Re-read every file the trail will reference. Don't trust your earlier scan.
2. Open `templates/trail.md.tmpl` and write the trail using the template structure.
3. Cite code with `path/to/file.py:LINE` after every claim that came from the code. Numbers must be real.
4. Write in the user's voice (concrete, second-person, present tense). "You run X. Module Y receives the call." Not "The system processes the request through a pipeline of stages."
5. Stop after one trail. Tell the user it's ready. Wait for review.

For each ref:

1. Re-read the module end-to-end.
2. Open `templates/ref.md.tmpl` and write following the structure: data types, function signatures, design notes, invariants.
3. Every exported function gets covered. Skip private helpers unless they encode an invariant worth surfacing.
4. Stop after one ref. Wait for review.

**Forbidden in Phase 2:** batch generation. Do not write three trails in one turn. Do not write a trail and a ref in the same turn. One file, one review, then move on. This is not optional — it is the entire reason the package exists. Batch generation produces slop.

## Where things live

```
.learn-pack/                  # The skill (vendored in the host repo)
├── SKILL.md                  # This file
├── PRINCIPLES.md             # Anti-slop rules — read before writing
├── DESIGN.md                 # How and why the package is shaped this way
├── scripts/
│   ├── scaffold.sh           # Creates docs/learn/ skeleton + empty manifest
│   └── install.sh            # Wires up Claude Code and Codex CLI
├── templates/
│   ├── README.md.tmpl
│   ├── trail.md.tmpl
│   ├── ref.md.tmpl
│   └── manifest.yml.tmpl
└── examples/
    └── marginalia/           # The original learn pack as worked reference

docs/learn/                   # Your output (in the host repo)
├── README.md
├── manifest.yml
├── trail-0-*.md
├── trail-N-*.md
└── ref/
    └── ref-*.md
```

You write to `docs/learn/`. You never write to `.learn-pack/` while filling.

## Bootstrapping a fresh run

```bash
.learn-pack/scripts/scaffold.sh    # Creates docs/learn/ if missing
```

The scaffold script is intentionally tiny. It only creates the directory and an empty manifest stub. The interesting work is yours.

## Updating an existing learn pack

If `docs/learn/manifest.yml` already exists, treat it as the source of truth and update individual files in place. Don't blow away existing trails the user has edited.

## When you're done

The pack is done when:

1. Every entry in the manifest has a corresponding file in `docs/learn/`.
2. Every claim in every file points to a real code reference.
3. The README's napkin sketch matches the actual lifecycle.
4. A reader who has never seen the codebase can read trail-0 and answer "what does this system do, and what's the most important file?"
