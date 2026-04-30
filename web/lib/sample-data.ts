import type {
  AskResponse,
  CompanyView,
  DocumentView,
  EvidenceTarget,
  PackView,
} from "@/types/china-lens";

export const demoCompany: CompanyView = {
  id: "cmp_tencent_0700",
  display_name_en: "Tencent Holdings Limited",
  display_name_zh: "腾讯控股有限公司",
  ticker: "0700.HK",
  exchange: "HKEX",
};

export const demoDocuments: DocumentView[] = [
  {
    id: "doc_tencent_2024_annual",
    title: "Tencent 2024 Annual Report",
    filing_type: "annual_report",
    filing_date: "2025-03-20",
    source: "CNINFO",
    pages: 188,
  },
  {
    id: "doc_tencent_2024_interim",
    title: "Tencent 2024 Interim Report",
    filing_type: "interim_report",
    filing_date: "2024-08-21",
    source: "CNINFO",
    pages: 104,
  },
];

export const demoPack: PackView = {
  id: "pack_demo_001",
  company_id: demoCompany.id,
  status: "partial",
  time_range: "last annual + last 2 interim",
  build_logs: [
    "download complete",
    "extract complete",
    "translate complete",
    "summarize complete",
    "index complete",
  ],
  sections: [
    {
      id: "summary",
      title: "Summary",
      thesis: "What the filings actually say about the business, stitched together with citations.",
      key_points: ["Unsupported: Management disclosed confidence in long-term cloud demand."],
      findings: [
        {
          id: "finding_summary_1",
          claim_text: "Management disclosed confidence in long-term cloud demand.",
          status: "unsupported",
          citations: [],
          unknown_reason: "Not found in indexed sources",
        },
      ],
      unknowns: ["Not disclosed: named top customers in annual filing"],
      coverage_status: "incomplete",
      updated_at: new Date().toISOString(),
    },
    {
      id: "customers_suppliers",
      title: "Customers + Suppliers",
      thesis: "Concentration risk and disclosure quality.",
      key_points: [
        "Top five customers represented 24.3% of revenue; customer names were not disclosed.",
      ],
      findings: [
        {
          id: "finding_customer_1",
          claim_text:
            "Top five customers represented 24.3% of revenue; customer names were not disclosed.",
          status: "supported",
          citations: [
            {
              chunk_id: "chunk_top_customers",
              doc_id: "doc_tencent_2024_annual",
              page: 87,
              citation_label: "CNINFO 2024 Annual Report, p. 87, Table 12",
            },
          ],
        },
      ],
      unknowns: [],
      coverage_status: "partial",
      updated_at: new Date().toISOString(),
    },
    {
      id: "ownership_governance",
      title: "Ownership + Governance",
      thesis: "Control, board, and related-party disclosures.",
      key_points: ["The board has nine directors, including four independent directors."],
      findings: [
        {
          id: "finding_governance_1",
          claim_text: "The board has nine directors, including four independent directors.",
          status: "supported",
          citations: [
            {
              chunk_id: "chunk_governance",
              doc_id: "doc_tencent_2024_annual",
              page: 121,
              citation_label: "CNINFO 2024 Annual Report, p. 121",
            },
          ],
        },
      ],
      unknowns: [],
      coverage_status: "partial",
      updated_at: new Date().toISOString(),
    },
  ],
};

export const demoEvidenceTarget: EvidenceTarget = {
  chunk_id: "chunk_top_customers",
  doc_id: "doc_tencent_2024_annual",
  page: 87,
  text_zh: "前五大客户收入占集团总收入24.3%，未披露客户名称。",
  text_en: "Top five customers represented 24.3% of group revenue; customer names were not disclosed.",
  citation_label: "CNINFO 2024 Annual Report, p. 87, Table 12",
};

export const demoAskResponse: AskResponse = {
  not_found: false,
  guidance: "Open citations to verify original Chinese sources.",
  answer: [
    {
      text: "Top customer concentration is disclosed as 24.3%, and customer names are not disclosed.",
      citations: [
        {
          chunk_id: "chunk_top_customers",
          doc_id: "doc_tencent_2024_annual",
          page: 87,
          citation_label: "CNINFO 2024 Annual Report, p. 87, Table 12",
        },
      ],
    },
  ],
};
