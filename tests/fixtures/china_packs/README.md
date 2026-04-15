# China test pack fixtures

Packs in this directory are committed for offline test runs. The PDFs
are downloaded via `scripts/download_hk_prospectus.sh`; the packs
themselves are built via `scripts/build_hk_fixture_packs.py`.

Contents:
- `minimax_2024/` — IPO prospectus (716 pages) + extracted pack
- `zhipu_2024/` — IPO prospectus (504 pages) + extracted pack

Regenerate after modifying `edgarpack/hk/adapter.py`:
```bash
.venv/bin/python scripts/build_hk_fixture_packs.py
```
