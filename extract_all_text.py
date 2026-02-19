import fitz
from pathlib import Path

data_dir = Path("data")
pdfs = sorted(data_dir.glob("*.pdf"))

for pdf_path in pdfs:
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    
    out_name = pdf_path.stem + ".txt"
    with open(out_name, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{pdf_path.name}: {len(text)} chars, {doc.page_count} pages -> {out_name}")
    doc.close()
