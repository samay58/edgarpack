# Reports Map

`reports/` is for research outputs built from primary documents. Keep it
evidence-first: tables and ledgers before narrative claims, with enough source
material that another agent can audit the work.

## Durable Research Bundles

Use `reports/<slug>/` for committed research bundles. A durable bundle should
usually include:

- `README.md`: scope, question, and how to read the bundle.
- `source-ledger.csv` or an equivalent evidence ledger.
- Structured tables before narrative synthesis.
- `search-notes/` or `raw/` when intermediate source collection matters.

Current durable bundles:

- `saas-evolution/`
- `dominant-company-architecture/`
- `founder-control/`
- `founder-control-era/`

## Thread Drafts

Use `reports/threads/` for social/thread drafts and short publishable notes
derived from EdgarPack outputs. These are not canonical product docs and should
not be used as implementation plans.

## Local Generated Outputs

Generated HTML diffs and one-off render outputs are local artifacts. Put them in
`reports/local/` when you want to keep the tree tidy, or let CLI examples write
`reports/*.html`; both are ignored by git.

## Placement Rules

- New investor/research work: `reports/<slug>/`.
- Thread-style prose: `reports/threads/`.
- One-off generated HTML or scratch exports: `reports/local/` or ignored
  `reports/*.html`.
- Product docs: `docs/`, not `reports/`.
