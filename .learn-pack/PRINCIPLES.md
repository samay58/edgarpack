# Principles

The difference between a learn pack and AI slop. Read this before you write a single line.

## 1. Story before reference

Trails come first. A reader who lands in `docs/learn/` and reads only the README and trail-0 should walk away knowing what the system does and how it does it. Refs are dictionaries: useful, but only after you have the story.

If you find yourself writing "the foo module exposes a bar function which takes a baz parameter", stop. That belongs in a ref. A trail says "you call `foo.bar(baz)`, here's what happens next."

## 2. Concrete actions, not abstract systems

Every trail starts with something a person does. "You save a draft file." "You run `edgarpack query NVDA`." "An HTTP request arrives at /pack/build." Never "the system handles requests" or "the architecture supports multiple flows."

If the trail can't be triggered by a single concrete action, it's not a trail. It's a survey, and surveys belong in the README, not in trails.

Lead with the command, then explain. Open the trail, and each step that has one, with the thing the reader runs and the output that comes back, then put the explanation underneath. The reader runs it, looks at real output, and only then reads why. A trail should be followable start to finish without the reader ever opening the source. The citations are how they go deeper when they want to, not a toll they pay to follow along.

## 3. Cite the code, don't paste it

Every non-obvious claim ends with a reference: `path/to/file.py:LINE`. Line numbers must be real. If the code moves, the trail moves with it. A learn pack with stale references is worse than no learn pack. It teaches the wrong thing.

When you cite a function, name it: `edgarpack/sec/client.py:fetch_filing()`. When you cite a section, give the line range: `edgarpack/parse/sectionize.py:120-180`.

Describe what the code does; do not reproduce its body. A trail is not a second copy of the source. Pasting function bodies is the most common way a learn pack turns into slop: the paste goes stale the moment the code moves, and the reader skims it instead of opening the real thing. Say what the code does in plain prose and cite the line.

Runnable commands and a few lines of representative output are a different thing, and they are welcome. Show the reader what to type and what comes back. That is the trail's spine, not implementation source. When several claims in a section came from the code, collect their references into one list at the end of the trail instead of tagging every paragraph.

## 4. Plain text projection > raw structure

Diff what the user sees, not what the parser sees. Same applies to docs. Describe what the code does in the situations the reader will encounter, not all the situations the code could theoretically encounter. Edge cases belong in refs, behavior contracts, or tests, not in trails.

## 5. Voice rules (the anti-slop kill list)

These are not stylistic preferences. Every one of these is an AI tell that destroys the reader's trust. Zero tolerance:

- **No em-dashes (—).** Use a period or a semicolon.
- **No "Furthermore", "Moreover", "Additionally", "In addition".** Just start the sentence.
- **No "delve", "delving into", "navigate", "leverage" (as a verb).** Plain English verbs only.
- **No "this comprehensive guide", "in this section we will", "let's explore".** Just do the thing.
- **No flowery preambles.** "It's important to understand that..." Cut. "First, let's note that..." Cut.
- **No bold headers in flowing prose.** Bold is for the rare term that needs to pop. If every paragraph has a bold lead-in, none of them do.
- **No exclamation points.** Ever.
- **No "key insight:" / "important note:" / "TL;DR:".** If it's important, the prose carries it.
- **No three-beat parallel structure where every paragraph is the same length.** Vary deliberately. Short sentence. Then a longer one that earns its length by carrying information the short one couldn't. Then back to short.
- **No "it's worth noting" / "as we'll see" / "as mentioned earlier".** Self-referential filler.
- **No numbered section headers.** `## The rate limiter`, not `## 4. The rate limiter`. Numbers imply an order the reader has to follow; descriptive headers let them skim straight to what they need.
- **Sentence case in headers, not Title Case.** `## How to use this`, not `## How To Use This`.
- **No metadata chrome at the top of a trail.** A bold `**Time**` / `**Prereq**` / `**Covers**` block reads as a generated form. One plain line, `Time: about N minutes`, is enough. Fold any prerequisite into the opening sentence and leave the module list in the manifest.
- **No recap or quiz sections.** A closing `## Recap` that restates the trail, or a `## Check your understanding` question block, is textbook scaffolding. If a trail needs a recap to make sense, it was structured wrong. End on the consolidated citation list instead.

## 6. Second-person, present tense, active voice

"You run the command. The CLI parses your arguments. The handler dispatches to the harvester."

Not "The command is run by the user. Arguments are parsed by the CLI. The handler dispatches to the harvester."

Not "When the user runs the command, the CLI parses the arguments, and then the handler dispatches to the harvester."

Second person creates the seat at the table the reader needs. Present tense keeps the prose immediate. Active voice removes the four wasted words in every sentence.

## 7. Write the napkin sketch first

Before you plan a single trail, draw the lifecycle as a 6-12 line ascii diagram in plain English verbs. If you can't draw it, you don't understand the system yet. Read more code. Try again.

The napkin sketch is the first thing a reader sees. It's also the artifact that proves to you that you have a real model of the system before you start writing about it.

## 8. Link, don't restate

If trail-2 needs context that trail-0 already covered, link to trail-0. Don't recap. Recapping is how learn packs rot: the recap drifts from the original and now there are two slightly-different versions of the same explanation.

## 9. Omissions are part of the design

The manifest has an `omitted:` section for a reason. State what you deliberately skipped, in one line, with a one-line reason. Future runs will pick this up and reconsider. Silent omissions are bugs.

## 10. The done bar

A learn pack is done when a reader who has never touched the codebase can:

1. Read the README and trail-0.
2. Open the most important source file you cited.
3. Make a one-line change with confidence about what will and won't break.

If they can't do that, the pack isn't done yet. Add the trail or ref that closes the gap.
