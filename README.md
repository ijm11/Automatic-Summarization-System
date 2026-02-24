# Automatic Summarization of BOE Scholarship Announcements

This project extracts structured data from Spanish BOE (Boletín Oficial del Estado) scholarship PDFs and generates abstractive summaries using multiple language models.

## Project Structure

```
data/                        # Source PDFs (5 academic years)
extractor_becas.py           # Extraction pipeline (PDF → JSON/CSV)
extract_all_text.py          # Helper: extracts raw text from PDFs
generador_resumenes.py       # Generation pipeline (JSON → summaries)
becas_estructuradas.json     # Extracted structured data
becas_estructuradas.csv      # Same data in flat CSV format
resumenes_generados.json     # Generated summaries (18 total)
extraction_report.md         # Report on the extraction process
generation_report.md         # Report on the generation process
```

## Setup

```bash
pip install -r requirements.txt
```

For the generation step, you need a DeepSeek API key. Copy the example and add your key:

```bash
cp .env.example .env
# Edit .env and paste your API key
```

## Running

### 1. Extract text from PDFs (optional — .txt files already included)

```bash
python extract_all_text.py
```

### 2. Extract structured data

```bash
python extractor_becas.py
```

Outputs: `becas_estructuradas.json` and `becas_estructuradas.csv`

### 3. Generate summaries

```bash
python generador_resumenes.py
```

Outputs: `resumenes_generados.json`

This runs three models (GPT-2 local, DeepSeek-Chat, DeepSeek-Reasoner) on each year plus a combined summary. GPT-2 runs locally; the two DeepSeek models require the API key.
