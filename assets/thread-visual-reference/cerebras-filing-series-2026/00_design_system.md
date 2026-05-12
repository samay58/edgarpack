# Cerebras Filing Series: Visual System Notes

These notes capture the intended design system for the image set. The images are generated PNGs, so the exact fonts are not embedded as reusable type assets, but this document describes the palette, type direction, spacing, and visual language used across the series.

## Included images

- `01_revenue_surged.png`: 1122 x 1402px, 1.30 MB
- `02_customer_frame_flipped.png`: 1122 x 1402px, 1.49 MB
- `03_big_customers_spent_more.png`: 1122 x 1402px, 1.24 MB
- `04_openai_warrant_changed_story.png`: 1122 x 1402px, 1.59 MB
- `05_20_votes_per_share.png`: 1122 x 1402px, 1.29 MB
- `06_cerebras_vs_nvidia.png`: 1122 x 1402px, 1.63 MB
- `07_market_framing_shifted.png`: 1122 x 1402px, 1.48 MB
- `08_ipo_got_upsized.png`: 1122 x 1402px, 1.57 MB

## Design direction

A premium editorial-compute aesthetic: crisp, restrained, and slightly edgy, with the polish of a design-led infrastructure company. The system sits between a high-end research deck and a modern product launch page: airy, precise, and intentionally sparse, but with one aggressive orange accent to keep the visuals alive.

The goal is not a generic finance infographic. The mood is: frontier compute, public-market filing analysis, modern software studio, sharp research memo.

## Palette

Approximate color system:

| Role | Hex | Usage |
|---|---:|---|
| Warm ivory background | `#F8F4EA` | Main canvas, keeps the series warm and editorial |
| Soft paper highlight | `#FFF9EF` | Interior cards and quiet content areas |
| Deep charcoal | `#111111` | Primary headlines, key body text |
| Muted charcoal | `#3F4246` | Secondary copy and explanatory labels |
| Hairline gray | `#D8D2C8` | Dividers, grids, axis lines, panel boundaries |
| Accent orange | `#FF4D00` | Primary visual punch, bars, active metrics, slashes |
| Copper orange | `#E95A1A` | Gradient depth and halftone glow |
| Pale orange wash | `#FFF0E6` | Very light backgrounds behind emphasis blocks |
| Near-black accent | `#080808` | Used sparingly for high-impact contrast, especially hardware callouts |

## Typography direction

Suggested type stack if recreating manually:

- **Display serif:** Canela, Editorial New, GT Sectra, PP Editorial New, or a high-contrast Didot/Bodoni-style serif.
- **Sans-serif:** IBM Plex Sans, Mona Sans, Suisse Intl, ABC Diatype, or Neue Haas Grotesk.
- **Mono / micro-labels:** Berkeley Mono, IBM Plex Mono, or SF Mono.

Rules:

- Use the serif for the emotional idea: title, large caption, major numeric hero moments.
- Use the sans for captions, table labels, explanatory copy, and source lines.
- Use uppercase tracking for system labels like `CEREBRAS FILINGS SERIES`, row headers, and small metric labels.
- Keep line-height generous. The best slides in the set breathe.

## Layout system

Canvas:

- 4:5 portrait social format.
- Generated at approximately `1122 x 1402px`.
- Optimized for X/Twitter and LinkedIn image embeds.

Structure:

- Small circular index marker in the top-left.
- Thin horizontal rule connecting the index to the system label.
- Large, left-weighted headline with generous top whitespace.
- Main content area uses two-column or modular grid layouts.
- Footer has a small dot-grid motif, a thin baseline, a source line, and a tiny orange slash.

Spacing principles:

- Let large serif text breathe.
- Avoid more than 2 to 3 dense text blocks per visual zone.
- Use thin rules instead of heavy boxes whenever possible.
- Use cards only when they clarify hierarchy.

## Visual motifs

Recurring elements:

- Orange halftone / ray mesh in the upper-right as the "compute energy" motif.
- Thin gray rules and dotted gridlines.
- Small circular icons with restrained line art.
- Orange slashes and underlines as directional accents.
- Simple data marks: bars, line charts, cohort nodes, comparison tables.

Tone:

- Confident, not loud.
- Analytical, not academic.
- Product-led, not consultancy-deck generic.
- Designed for smart readers who want the punchline fast.

## Slide-specific notes

1. **Revenue surged**: the core visual is revenue scale. The right rail keeps financial nuance without overwhelming the viewer.
2. **Customer frame flipped**: before/after composition. Single-customer dependence becomes named cohort.
3. **Big customers spent more**: the cleanest slide. One growth line, two supporting callouts, no bottom takeaway.
4. **OpenAI warrant**: modular relationship map: customer, creditor, equity holder.
5. **20 votes per share**: governance hero slide. The large `20` is the visual center of gravity.
6. **Cerebras vs. NVIDIA**: more dramatic hardware slide. The benchmark is secondary to the public-filing positioning.
7. **Market framing shifted**: training-led TAM vs inference-led positioning.
8. **IPO got upsized**: table-first slide, with the edgarpack diff note called out as the mechanism that made the changes explicit.

## Reuse guidance

To keep the series cohesive, use:

- Same background and footer treatment.
- Same index marker and system label placement.
- Same orange accent discipline.
- Same serif/sans hierarchy.
- A different composition per slide so the thread does not feel repetitive.

Avoid:

- Dense paragraphs.
- Too many icon cards.
- More than one dominant orange region per slide.
- Generic infographic tropes, especially oversized clip-art icons or unnecessary bottom takeaways.

## Source language

Standard footer pattern:

`Source: Cerebras S-1 filings, via edgarpack diff.`

For the S-1/A amendment slide:

`Source: May 4 and May 11 Cerebras S-1/A filings, via edgarpack diff.`
