import fitz  # PyMuPDF
from pathlib import Path
import sys

data_dir = Path("data")
pdfs = sorted(data_dir.glob("*.pdf"))

for pdf_path in pdfs:
    print(f"\n{'='*100}")
    print(f"FILE: {pdf_path.name}")
    print(f"{'='*100}")
    doc = fitz.open(pdf_path)
    text = ""
    for i, page in enumerate(doc):
        page_text = page.get_text()
        text += page_text
    # Print first 12000 chars to get the structure
    print(text[:12000])
    print(f"\n--- TOTAL LENGTH: {len(text)} chars, {doc.page_count} pages ---")
    doc.close()
