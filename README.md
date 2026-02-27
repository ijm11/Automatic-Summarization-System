# Automatic Summarization & Evaluation of BOE Scholarship Announcements

This project provides a full pipeline to extract, summarize, and evaluate scholarship information from the Spanish Official State Gazette (BOE). It uses a hybrid approach combining local models (GPT-2) and high-performance APIs (DeepSeek) to provide insights for students.

## 🚀 Overview

The system works in three main stages:
1.  **Extraction**: PDFs are parsed using regex to extract structured data (amounts, thresholds, deadlines).
2.  **Generation**: Structured data is turned into natural language summaries in English using various LLMs.
3.  **Evaluation**: Summaries are audited for accuracy, linguistic quality, and hallucinations using BLEU, ROUGE, BERTScore, and Vectara HHEM.

## 📁 Project Structure

```text
.
├── data/                       # Source PDFs (2021-2026 academic years)
├── extractor_becas.py          # PDF → JSON/CSV extraction logic
├── generador_resumenes.py      # JSON → Summary generation (GPT-2, DeepSeek)
├── evaluador_resumenes_v1.py   # Multi-metric performance auditor (BLEU, BERTScore)
├── hallucination_evaluator.py  # Specific hallucination check (Vectara HHEM)
├── becas_estructuradas.json    # Extracted facts (The "Truth")
├── resumenes_generados.json    # Generated text from all models
├── resultados_evaluacion/      # Dashboards, heatmaps, and detail reports
└── requirements.txt            # System dependencies
```

## 🛠️ Setup

1.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **API Configuration**:
    Create a `.env` file and add your DeepSeek key:
    ```text
    DEEPSEEK_API_KEY=your_key_here
    ```

## 🏃 Execution Guide

Follow these steps in order to complete the full pipeline:

### 1. Data Extraction
Process the raw PDFs into a structured format.
```bash
python extractor_becas.py
```
*Outputs: `becas_estructuradas.json`, `becas_estructuradas.csv`*

### 2. Summary Generation
Generate summaries using local GPT-2 and DeepSeek APIs.
```bash
python generador_resumenes.py
```
*Outputs: `resumenes_generados.json`*

### 3. Performance Audit
Run the evaluation suite to compare model performance and generate dashboards.
```bash
python evaluador_resumenes_v1.py
```
*Outputs: `resultados_evaluacion/dashboard_final_completo.png`*

### 4. Hallucination Detection
Run a specialized check to see which models "invented" facts.
```bash
python hallucination_evaluator.py
```

## 📊 Evaluation Metrics

-   **Recall %**: Measures if the model captured all the numbers from the data.
-   **Hallucination Rate**: Measures numbers present in the summary that weren't in the data.
-   **ROUGE-L / BLEU**: Classical linguistic similarity against a human reference.
-   **BERTScore**: Semantic similarity comparing the English summary to the original Spanish PDF.
-   **HHEM Score**: Probability of the text being a truthful entailment of the facts.

---
*Developed as part of the APLN University Project.*
