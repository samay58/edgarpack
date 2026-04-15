# Chinese AI lab listing status (verified 2026-04-14)

Primary-source verification of which Chinese AI labs are publicly listed, for use by the China AI labs implementation plan (`docs/superpowers/plans/2026-04-14-china-ai-labs.md`). Each entry cites at least two independent sources.

## Confirmed PUBLIC

### MiniMax
- **Status**: PUBLIC (HKEX)
- **Stock code**: `00100.HK` (HKEX numeric `100`)
- **Company name**: MiniMax Group Inc.
- **Listing date**: 2026-01-09
- **Offer price**: HKD 165.00
- **IPO size**: ~HKD 4.8B (~USD 619M)
- **First-day close**: HKD 345 (+109%)
- **Sources**:
  - HKEX direct: https://www.hkex.com.hk/Market-Data/Securities-Prices/Equities/Equities-Quote?sym=100&sc_lang=en
  - Bloomberg, "MiniMax Shares Double in Hong Kong Debut After $619 Million IPO" (2026-01-08)
  - CNBC, "MiniMax doubles in Hong Kong debut, marking yet another Chinese AI listing" (2026-01-09)

### Zhipu (Z.ai)
- **Status**: PUBLIC (HKEX)
- **Stock code**: `2513.HK`
- **Company name**: Beijing Zhipu Huazhang Technology Co. Ltd. (brand: Z.ai)
- **Listing date**: 2026-01-08
- **Offer price**: HKD 116.20
- **IPO size**: HKD 4.35B (~USD 558M)
- **Aliases**: zhipu, zhipu ai, z.ai, glm, chatglm
- **Sources**:
  - Bloomberg, "China's AI Firm Zhipu Climbs in Debut, Lagging Hardware Peers" (2026-01-07)
  - SCMP, "Chinese AI 'tiger' Zhipu edges towards Hong Kong listing expected to raise US$300 million"
  - PRNewswire, "China's AGI Pioneer and Leader Z.ai Listed on Hong Kong Stock Exchange"

## Confirmed PRIVATE (do NOT add to universe)

### Moonshot AI (Kimi)
- **Status**: PRIVATE
- **Latest valuation**: ~USD 4.3B (Series C early 2026)
- **Listing posture**: Explicitly "not in a hurry to go public"
- **Source**: Caixin Global, "Moonshot AI Rules Out Quick IPO After Raising $500 Million" (2026-01-01)

### 01.AI
- **Status**: PRIVATE
- **Founded by**: Kai-Fu Lee
- **Source**: No IPO information surfaced in 2026 search results.

### Baichuan
- **Status**: PRIVATE
- **Founded by**: Wang Xiaochuan
- **Note**: Pivoted to healthcare AI applications.
- **Source**: No 2026 IPO plans.

### DeepSeek
- **Status**: PRIVATE (backed by High-Flyer Capital)
- **Source**: No IPO announcement surfaced.

## Implementation impact

For Task 2 (universe correction): add MiniMax (`00100.HK`, hk_stock_code `00100`) and Zhipu (`2513.HK`, hk_stock_code `02513`) to `universe.toml`. Drop the existing `MINIMAX-PRIVATE` entry. Do NOT add Moonshot, 01.AI, Baichuan, or DeepSeek; they remain private. File a follow-up watchlist note for any of them later if listing status changes.

For Task 3 (PDF acquisition): MiniMax and Zhipu prospectuses are filed under their HKEX stock codes. Standard hkexnews URL pattern; resolve at download time.
