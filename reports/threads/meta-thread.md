# Meta's Last Three 10-Ks, Diffed

*Drafted via Spiral (Tweet elite). Source: edgarpack diff of Meta's last three 10-Ks. CIK 0001326801.*

---

**1/** I diffed Meta's last three 10-Ks using edgarpack.

FY22 → FY23 change intensity: 28.7%.
FY23 → FY24: 27.8%.

Nearly a quarter of the filing rewritten each year. Steady churn, driven almost entirely by external pressure. The opposite of NVDA.

**2/** Meta rewrote its mission statement in FY24.

Old: "Give people the power to build community and bring the world closer together."
New: "Build the future of human connection and the technology that makes it possible."

Companies almost never do this. When they do, it means the old identity stopped being useful.

**3/** The metaverse got reframed. "Next evolution in social technology" became "next computing platform and the future of social interaction."

That's Reality Labs repositioning from a social bet to a generational compute bet. Subtle language. Massive strategic signal.

**4/** Now they're saying the quiet part out loud. Reality Labs operating drag disclosed at headline level for the first time:

"reduced our 2024 overall operating profit by approximately $17.73 billion, and we expect our Reality Labs investments and operating losses to increase in 2025."

This is not a side project. It is a second company burning inside the first.

**5/** Capital return pivot. First-ever quarterly dividend ($0.50/share), declared February 2024. Additional $50B buyback authorization in January 2024. Stock: $354 → $585 over the year.

Meta went from Metaverse penalty box to rewarding shareholders in twelve months flat.

**6/** The regulator war diary:

- €1.2B IDPC fine (May 2023, Standard Contractual Clauses)
- €798M EU Marketplace antitrust fine (Nov 18, 2024)
- DSA applied August 2023; DMA enforceable March 2024
- EC opened DSA investigation into FB/IG (April 30, 2024)
- CFPB NORA process, financial advertising (Sept 18, 2024)
- EU preliminary finding: "subscription for no ads" doesn't comply with DMA (July 1, 2024)

This is the real driver of Meta's filing churn. Regulators are co-authoring the 10-K.

**7/** Generative AI promoted to standalone risk factor in FY24. Specific callouts: deepfakes, election misinformation, IP infringement, defamation.

A year earlier, this lived inside general risk language. Now it gets its own section. The risk disclosures are catching up to the product roadmap.

**8/** Best detail in the entire filing. Zuckerberg's key-person risk got specific new language: he participates in "combat sports, extreme sports, and recreational aviation."

Your CEO's hobbies are now a material risk to the business. This is real.

**9/** Pre-emptive content moderation disclosure in FY24:

"in January 2025, we announced certain changes to our content policies and enforcement efforts to further free expression on our platform and mitigate over-enforcement."

They filed the legal framing before the news cycle landed. The 10-K as comms strategy.

**10/** Product map shifts. Threads and WhatsApp Channels got their first dedicated paragraphs in FY23. Reality Labs vocabulary tracked the hardware: VR became "VR and MR" in FY23 (Quest 3 passthrough era), then expanded to include AR in FY24.

The language follows the product roadmap with a one-year lag.

**11/** Quiet changes that got no coverage:

- FX losses 4.5x'd: $81M (2022) → $366M (2023). Zero headlines.
- Item 1C Cybersecurity section added in FY23 (new SEC rule).
- FY23 metric sunset: DAU/MAU/ARPU/MAP retired for DAP/ARPP starting Q1 2024.
- 2022 layoffs memorialized as $4.6B restructuring ($4.10B FoA + $515M RL), aged off by FY23/24.

**12/** Quest inventory risk elevated to its own risk factor in FY24. Includes explicit tariff language. Meta is a consumer electronics company with real supply chain exposure now, and the filing finally admits it.

**13/** The frame.

Meta's filing churn holds steady at ~28%. External forces drive it: DMA, DSA, IDPC fines, generative AI risk factors. NVDA's churn drops from 22% to 13% as it narrows around fewer, larger AI customers.

Two companies. Two opposite trajectories. The 10-K tells you which story is being written for them and which one they're choosing to write.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The two commands that produced this thread:

```bash
# Build Meta's last three 10-Ks
edgarpack build Meta --form 10-K --last 3 --out ./packs

# Diff FY23 → FY24 in full format
edgarpack diff \
  --before packs/0001326801/<FY23-accession> \
  --after  packs/0001326801/<FY24-accession> \
  --format full > meta_23_24.diff
```

The combat-sports clause, the €798M Marketplace fine, the mission rewrite, the Reality Labs $17.73B drag — all single paragraphs deep inside hundred-page filings. The diff makes them findable. The tool didn't write the thread. It made the thread writable.
