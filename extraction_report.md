# Data Extraction Report

## Overview

We built a Python-based extraction system (`extractor_becas.py`) that reads five official BOE scholarship PDFs (academic years 2021-2022 through 2025-2026) using PyMuPDF and extracts structured data into JSON and CSV files. The system uses regular expressions to locate and parse specific articles and sections within each document.

Each PDF follows a similar legal structure (numbered articles, chapters, and sections), but the formatting varies across years — for example, income thresholds shifted from a list format (2021-2023) to a table format (2024-2026), and some provisions like the Canary Islands FP supplement were only introduced in later years. We designed the extractors to handle these variations robustly.

## Extracted Data Categories

From each PDF, we extract **17 top-level fields** containing **72-82 individual data points** per document. The data breaks down as follows:

### 1. General Information
- **Academic year**: Detected from the document body or filename (e.g., "2025-2026").
- **Educational programs** (Article 3): The full list of eligible programs — bachillerato, vocational training (FP), university degrees (grado and master), language studies, art schools, sports studies, and religious studies. Doctoral and proprietary university programs are explicitly excluded.

### 2. Scholarship Amounts (Article 11)
We extract six fixed monetary components:

| Component | Description | Example (2025-26) |
|---|---|---|
| `cuantia_renta_fija` | Fixed income-linked amount | 1,700.00 EUR |
| `cuantia_residencia` | Residence allowance | 2,700.00 EUR |
| `beca_basica` | Basic scholarship (non-university) | 300.00 EUR |
| `cuantia_variable_minima` | Minimum variable amount | 60.00 EUR |
| `excelencia_min` | Excellence minimum | 50 EUR |
| `excelencia_max` | Excellence maximum | 125 EUR |

### 3. Excellence Grade Brackets (Article 8)
The four-tier excellence table, linking grade ranges to euro amounts:

| Grade Range | Amount |
|---|---|
| 8.00 – 8.49 | 50 EUR |
| 8.50 – 8.99 | 75 EUR |
| 9.00 – 9.49 | 100 EUR |
| 9.50+ | 125 EUR |

### 4. Income Thresholds (Article 19)
Three threshold levels (Umbral 1, 2, 3) that determine eligibility for different scholarship components. Each level specifies maximum family income for families of 1 to 8 members. For example, in 2025-26, a 4-member family needs income below 22,107 EUR for Threshold 1 (fixed income component) or below 40,773 EUR for Threshold 3 (tuition + excellence).

### 5. Asset/Patrimonio Thresholds (Article 20)
Four asset limits that disqualify applicants regardless of income:
- Urban properties (excluding main home): max 42,900 EUR
- Rural constructions: max 42,900 EUR
- Rural land: max 13,130 EUR per family member
- Capital gains / movable assets: max 1,700 EUR

### 6. Academic Requirements (Articles 23-24)
- **Full-time enrollment**: 60 credits minimum.
- **Partial enrollment**: 30 credits minimum (only tuition + minimum variable awarded).
- **University entry grade**: 5.00 points required for first-year students.
- **Credit pass-rate by knowledge area** (for returning students):

| Area | Minimum Pass Rate |
|---|---|
| Arts & Humanities | 90% |
| Sciences | 65% |
| Social Sciences & Law | 90% |
| Health Sciences | 80% |
| Engineering & Architecture | 65% |

### 7. Insular/Ceuta-Melilla Supplements (Article 12)
Additional amounts for students in island territories or Ceuta/Melilla who need air or sea transport:
- Basic supplement: 442 EUR
- Remote islands (Lanzarote, Fuerteventura, La Gomera, El Hierro, La Palma, Menorca, Ibiza, Formentera): 623 EUR
- Inter-island to Peninsula: 888 / 937 EUR
- FP students in Canary Islands: extra 300 EUR (from 2023-24 onwards)

### 8. Income Deductions (Article 18)
Deductions applied to reduce the computed family income:
- Large family (general): 525 EUR per sibling
- Large family (special): 800 EUR per sibling
- Disability 33%+: 1,811 EUR per affected member
- Disability 65%+: 2,881 EUR per affected member
- University applicant with 65%+ disability: 4,000 EUR
- Sibling studying away from home: 1,176 EUR each
- Orphan: 20% of family income
- Single-parent family: 500 EUR

### 9. Disability Provisions (Article 13)
- Students with 65%+ disability may reduce their credit load.
- Students with 25-65% disability get a 25% increase in fixed amounts.
- Disabled students who enroll full-time (without reducing load) get a 50% increase in fixed amounts.

### 10. Application Deadlines
- Start and end dates for the application period.
- Separate deadlines for university vs. non-university students (when applicable).
- General cutoff date (typically December 31st).

## Extraction Methodology

The system follows this pipeline for each PDF:

1. **Text extraction**: PyMuPDF reads all pages and concatenates the raw text.
2. **Section isolation**: For each data category, we locate the relevant article using regex (e.g., `Artículo 20\. Umbrales indicativos de patrimonio familiar`) and extract the text up to the next article boundary.
3. **Data parsing**: Within each section, targeted regex patterns capture specific values — euro amounts, percentages, dates, and structured tables.
4. **Cross-year robustness**: We handle format variations by using multiple parsing strategies (e.g., list-based vs. table-based thresholds) and flexible whitespace matching to account for PDF text extraction artifacts like mid-word line breaks.

## Output Files

- **`becas_estructuradas.json`**: Full hierarchical dataset with nested objects for thresholds, deductions, and supplements.
- **`becas_estructuradas.csv`**: Flattened version where nested fields are serialized as JSON strings, suitable for spreadsheet analysis.

## Consistency Across Years

All 17 fields are successfully extracted from all 5 PDFs. Minor variations exist:
- The residence amount increased over time (1,600 → 2,500 → 2,700 EUR).
- The FP Canarias supplement (300 EUR) only appears from 2023-24 onwards.
- Income thresholds changed from text-based ("Familias de un miembro") to numeric table format in 2024-25.
- The 25% disability increment provision appears explicitly only in 2025-26.

These are genuine differences in the regulations, not extraction failures.
