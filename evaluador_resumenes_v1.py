import json
import re
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import nltk
from pathlib import Path
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction

# ──────────────────────────────────────────────
# 1. Setup and Library Checks
# ──────────────────────────────────────────────

# We try to import specialized metrics. If they aren't installed, we notify the user.
try:
    from rouge_score import rouge_scorer
    HAS_NLP_METRICS = True
except ImportError:
    HAS_NLP_METRICS = False

try:
    from bert_score import score as bert_score
    HAS_BERTSCORE = True
except ImportError:
    print("⚠️ bert-score is not installed. Run: pip install bert-score")
    HAS_BERTSCORE = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    print("⚠️ pypdf is not installed. Run: pip install pypdf")
    HAS_PYPDF = False


class NLGPerformanceAudit:
    """
    This auditor compares AI-generated summaries against a "Gold Standard" or the original PDF.
    It uses numbers, ROUGE/BLEU, and BERTScore to see which model is best.
    """
    def __init__(self, data_path="becas_estructuradas.json", gen_path="resumenes_generados.json", docs_dir="data"):
        self.data_path = data_path
        self.gen_path = gen_path
        self.docs_dir = Path(docs_dir)
        self.results = []
        # Folder to save our charts and results
        self.output_dir = Path("resultados_evaluacion")
        self.output_dir.mkdir(exist_ok=True)

    def _load_data(self):
        """Helper to load our JSON files."""
        if not Path(self.data_path).exists() or not Path(self.gen_path).exists():
            print("❌ Input files not found.")
            return False
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.ground_truth = json.load(f)
        with open(self.gen_path, "r", encoding="utf-8") as f:
            self.generated = json.load(f)
        return True

    def _clean_text(self, text):
        """
        Cleans text by removing symbols, currency names, and extra dots.
        This helps ROUGE/BLEU focus on the content, not just punctuation.
        """
        if not text: return ""
        text = text.lower()
        # Remove common "noise" words
        text = re.sub(r'€|euros|euro|cuantía|importe|monto', '', text)
        # Remove thousands separators (like the dot in 1.200)
        text = re.sub(r'(?<=\d)[\.,](?=\d{3})', '', text) 
        # Remove empty decimals (.00)
        text = re.sub(r'[\.,]00\b', '', text) 
        # Remove all special characters
        text = re.sub(r'[^\w\s\d]', ' ', text)
        return " ".join(text.split())

    def _extract_numbers(self, obj):
        """Extracts every number from a complex JSON object to check for accuracy."""
        numbers = set()
        if isinstance(obj, (dict, list)):
            items = obj.values() if isinstance(obj, dict) else obj
            for i in items:
                numbers.update(self._extract_numbers(i))
        elif isinstance(obj, (int, float, str)):
            matches = re.findall(r"\d+(?:[\.,]\d+)?", str(obj))
            for m in matches:
                # Clean the number to compare "1.200" with "1200"
                clean = m.replace(".", "").replace(",", "")
                if len(clean) >= 2: # Ignore single digits like "1" or "2"
                    numbers.add(clean)
        return numbers

    def _load_pdf_text(self, filename):
        """Reads the full text from the original PDF to use in semantic evaluation."""
        pdf_path = self.docs_dir / filename
        if not pdf_path.exists():
            return ""
        text = ""
        if HAS_PYPDF:
            try:
                reader = pypdf.PdfReader(pdf_path)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            except Exception:
                pass
        return text

    def run_evaluation(self):
        """The main evaluation loop comparing AI vs Human standards."""
        # This is our manually verified "perfect" summary for each year.
        gold_standards = {
            "2021-2022": "This summary outlines the official Spanish government scholarships for the 2021-2022 academic year. The grants cover a wide range of post-compulsory and higher education programs, including high school, vocational training, arts, language studies, and university degrees (bachelor's and master's). PhDs and specialization courses are excluded. The financial aid consists of several components. A basic grant of 300 euros is available to all eligible students. Additionally, there is a fixed income-based allowance of 1,700 euros and a residency allowance of 1,600 euros for those who must study away from home. A variable amount is also awarded, with a minimum guaranteed of 60 euros. Students with high academic performance receive an excellence bonus ranging from 50 to 125 euros, depending on their average grade. Students from insular territories (e.g., Canary or Balearic Islands) receive geographical supplements ranging from 442 to 937 euros. Eligibility is subject to strict income and asset thresholds. For a family of four, the maximum income limits for Thresholds 1, 2, and 3 are 21,054, 36,421, and 38,831 euros, respectively. Asset limits include a 42,900 euro cap on urban properties and a 1,700 euro cap on financial capital. Deductions apply for large families, single parents, or disability. Academically, first-year university students require a 5.00 admission grade. Returning students must pass a specific percentage of credits depending on their field: 90% for Arts/Humanities and Social Sciences, 80% for Health Sciences, and 65% for Sciences and Engineering. Students with a disability of 65% or more benefit from a reduced course load and a 50% tuition increase. The application deadlines were September 30, 2021 (non-university) and October 14, 2021 (university), with a final extension until December 31, 2021.",
            "2022-2023": "This document summarizes the official Spanish government educational grants for the 2022-2023 academic year. Eligible programs include non-university studies such as high school, vocational training, and official language courses, as well as university undergraduate and master's degrees. PhD programs are strictly excluded. The scholarship structure provides significant financial support. Eligible applicants receive a basic grant of 300 euros. Income-dependent students may receive a fixed allowance of 1,700 euros, while those required to relocate for their studies are entitled to a 1,600 euro residency allowance. Furthermore, a variable grant is provided with a minimum of 60 euros. An academic excellence bonus is awarded based on average grades, granting 50 euros for an 8.00 average, up to a maximum of 125 euros for a 9.50 average or higher. Insular students receive additional supplements ranging from 442 to 937 euros. Financial eligibility is determined by family income and wealth. For a four-member household, the income limits are set at 21,054 euros (Threshold 1), 36,421 euros (Threshold 2), and 38,831 euros (Threshold 3). Families cannot exceed asset limits, such as 42,900 euros for urban properties and 1,700 euros in liquid financial capital. Various income deductions are available for large families, single-parent households (500 euros), and disabilities. Academic requirements mandate that first-year university students achieve a 5.00 entry grade. To maintain the grant, university students must pass 90% of credits in Arts and Social Sciences, 80% in Health Sciences, or 65% in Engineering and Sciences. Students with a disability of at least 65% are eligible for a reduced academic load and a 50% increase in the full enrollment component. The application window for all students opened on March 30, 2022, and closed on May 12, 2022, with a final administrative deadline on December 31, 2022.",
            "2023-2024": "This text summarizes the official Spanish government scholarships for the 2023-2024 academic year. These grants cover non-university post-compulsory education (high school, vocational training, sports, and language studies) and official university degrees (bachelor's and master's). Third-cycle studies like PhDs are not eligible. The financial framework includes a basic grant of 300 euros for all qualifying students. A significant change this year is the increase in the residency allowance to 2,500 euros for students living away from home. The fixed income-based allowance remains at 1,700 euros. Students also receive a variable amount, guaranteed at a minimum of 60 euros. Academic excellence is rewarded with bonuses between 50 and 125 euros for grades above 8.00. Students from islands or remote areas receive specific geographical supplements ranging from 442 to 937 euros, plus a special 300 euro supplement for vocational training in the Canary Islands. Economic limits are strictly enforced. For a family of four, the income thresholds are 21,054 euros (Threshold 1), 36,421 euros (Threshold 2), and 38,831 euros (Threshold 3). Strict asset limits apply, including caps of 42,900 euros on urban properties and 1,700 euros on financial capital. Families can apply deductions for disabilities, large families, or single-parent households. Academic progression is required. First-year university students need a 5.00 access grade. Continuing university students must pass a specific percentage of their enrolled credits: 90% for Arts and Social Sciences, 80% for Health Sciences, and 65% for Sciences and Engineering. Students with a 65% or greater disability have a reduced course load requirement and receive a 50% tuition supplement. The application period for both university and non-university students was from March 27, 2023, to May 17, 2023, with a final overall deadline of December 31, 2023.",
            "2024-2025": "This is a comprehensive summary of the Spanish government scholarships for the 2024-2025 academic year. The grants support students in high school, vocational training, arts, language schools, and official university degrees (undergraduate and master's). Doctoral programs are excluded. The financial aid structure provides a basic grant of 300 euros. The residency allowance is set at 2,500 euros for students relocating for their studies, and the fixed income-linked allowance is 1,700 euros. A variable component ensures a minimum of 60 euros. Additionally, students with excellent academic records receive a bonus ranging from 50 to 125 euros (for grades of 9.50+). Extra geographical supplements, ranging from 442 to 937 euros, are granted to students from the islands, including a 300 euro bonus for vocational students in the Canary Islands. Economic thresholds have been updated using a new table format. For a four-member family, the new income limits are 22,107 euros for Threshold 1, 38,242 euros for Threshold 2, and 40,773 euros for Threshold 3. Asset limits remain strict, capping urban properties at 42,900 euros and liquid capital at 1,700 euros. Significant income deductions apply for large families, single parents, and students with disabilities. Academically, a 5.00 entry grade is required for first-year university students. To renew the grant, students must pass 90% of credits in Arts/Social Sciences, 80% in Health Sciences, or 65% in Sciences/Engineering. Special provisions exist for students with a disability of 65% or more, offering a reduced study load and a 50% increase in the enrollment grant. Applications for all educational levels had to be submitted between March 19, 2024, and May 10, 2024. The final deadline for administrative resolution was December 31, 2024.",
            "2025-2026": "This summary details the official Spanish government scholarships for the 2025-2026 academic year. The funding covers post-compulsory non-university education (such as high school, vocational training, and language courses) and official university bachelor's and master's degrees. PhDs and university-specific titles are not covered. The financial awards include a basic scholarship of 300 euros. This year, the residency allowance has been increased to 2,700 euros for students studying away from their family home. The fixed income allowance is maintained at 1,700 euros, and the minimum variable grant remains at 60 euros. Academic excellence bonuses range from 50 euros to 125 euros for high achievers. Students residing in insular territories receive supplements ranging from 442 to 937 euros, alongside a 300 euro supplement for Canary Islands vocational students. Financial eligibility is based on updated income tables. A family of four must fall below 22,107 euros for Threshold 1, 38,242 euros for Threshold 2, or 40,773 euros for Threshold 3. Asset limits restrict urban property values to 42,900 euros and financial capital to 1,700 euros. Income deductions are available for large families, single parents, and disabilities. Academic criteria require a 5.00 access grade for new university students. Continuing students must pass 90% of their credits in Arts/Humanities and Social Sciences, 80% in Health Sciences, or 65% in Sciences and Engineering. Notably, disability support has been expanded: students with a 25% to 65% disability receive a 25% enrollment increase, while those with 65% or more receive a 50% increase and a reduced course load. The general application period for all students runs from March 24, 2025, to May 14, 2025, with the absolute final deadline set for December 31, 2025."
        }

        if not self._load_data(): return
        
        try:
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
        except: pass

        # Load original PDF texts once to speed up BERTScore calcs
        pdf_texts = {}
        print("📄 Loading texts from original PDFs in the 'data' folder...")
        for item in self.ground_truth:
            year = item.get("curso_academico")
            filename = item.get("fichero")
            if year and filename:
                pdf_texts[year] = self._load_pdf_text(filename)

        facts_by_year = {item["curso_academico"]: item for item in self.ground_truth}
        
        if HAS_NLP_METRICS:
            r_scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
            smooth_func = SmoothingFunction().method1

        print("🧠 Evaluating summaries (this may take a while due to BERTScore calculation)...")
        for year, models in self.generated.items():
            ref_data = facts_by_year.get(year)
            if ref_data is None: continue
            
            ref_numbers = self._extract_numbers(ref_data)
            clean_ref = self._clean_text(gold_standards.get(year, ""))
            pdf_ref_text = pdf_texts.get(year, "") 

            for model_name, data in models.items():
                if "error" in data: continue
                
                gen_text = data.get("text", "")
                clean_sum = self._clean_text(gen_text)
                sum_numbers = self._extract_numbers(gen_text)

                # Metric 1: Numeric Accuracy (Did the model get the euros right?)
                hits = sum_numbers.intersection(ref_numbers)
                recall = (len(hits) / len(ref_numbers) * 100 if ref_numbers else 0)
                halluc_rate = (len(sum_numbers - ref_numbers) / len(sum_numbers) * 100 if sum_numbers else 0)

                # Metric 2: Language overlap (ROUGE/BLEU)
                rouge_score = 0.0
                bleu_score = 0.0
                if HAS_NLP_METRICS and clean_ref:
                    rouge_score = r_scorer.score(clean_ref, clean_sum)['rougeL'].fmeasure * 100
                    ref_tokens = nltk.word_tokenize(clean_ref)
                    gen_tokens = nltk.word_tokenize(clean_sum)
                    bleu_score = sentence_bleu([ref_tokens], gen_tokens, smoothing_function=smooth_func) * 100

                # Metric 3: Semantic Similarity (BERTScore vs original raw PDF text)
                bert_f1_score = 0.0
                if HAS_BERTSCORE and pdf_ref_text.strip() and gen_text.strip():
                    try:
                        # We use xlm-roberta because the source is Spanish but the summary is English
                        _, _, F1 = bert_score([gen_text], [pdf_ref_text], model_type="xlm-roberta-base", verbose=False)
                        bert_f1_score = F1.item() * 100
                    except Exception:
                        pass

                self.results.append({
                    "Year": year, 
                    "Model": model_name,
                    "Recall_%": round(recall, 2), 
                    "Halluc_Rate_%": round(halluc_rate, 2),
                    "ROUGE_L_%": round(rouge_score, 2), 
                    "BLEU_%": round(bleu_score, 2),
                    "BERTScore_F1_%": round(bert_f1_score, 2),
                    "Latency_s": round(data.get("time_seconds", 0), 2)
                })

        self._generate_outputs()

    def _generate_outputs(self):
        """Saves CSVs and creates the final visual dashboard."""
        df = pd.DataFrame(self.results)
        df_avg = df.groupby("Model").mean(numeric_only=True).reset_index()
        
        # Save detailed and cleaned spreadsheet reports
        df.to_csv(self.output_dir / "nlg_evaluation_detailed.csv", index=False)
        df_avg.to_csv(self.output_dir / "nlg_evaluation_summary_cleaned.csv", index=False)

        # Generate DASHBOARD using Seaborn
        sns.set_theme(style="whitegrid")
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle("Final Audit: Combined Metrics (2021-2026)", fontsize=20)
        
        metrics = [
            ("Recall_%", "Numeric Data Recall (%)"), 
            ("Halluc_Rate_%", "Numeric Hallucination (%)"), 
            ("ROUGE_L_%", "ROUGE-L (Short Reference)"), 
            ("BLEU_%", "BLEU (Short Reference)"), 
            ("BERTScore_F1_%", "BERTScore F1 (vs Original PDF)"),
            ("Latency_s", "Average Latency (s)")
        ]

        for i, (col, title) in enumerate(metrics):
            ax = axes[i//3, i%3]
            sns.barplot(x="Model", y=col, data=df_avg, ax=ax, palette="viridis", hue="Model", legend=False)
            ax.set_title(title)
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(self.output_dir / "dashboard_final_completo.png")
        print(f"✅ Dashboard generated at: {self.output_dir}")

    def plot_heatmap(self):
        """Creates a heatmap to see performance colors."""
        df = pd.DataFrame(self.results).groupby("Model").mean(numeric_only=True)
        plt.figure(figsize=(10, 6))
        sns.heatmap(df, annot=True, fmt=".2f", cmap="YlGnBu")
        plt.title("Heatmap: Comparative Performance")
        plt.savefig(self.output_dir / "heatmap_performance.png")
        plt.close()

    def plot_radar(self):
        """Generates Radar (Spider) charts for each model's hybrid profile."""
        df = pd.DataFrame(self.results).groupby("Model").mean(numeric_only=True).reset_index()
        metrics = ["Recall_%", "ROUGE_L_%", "BLEU_%", "BERTScore_F1_%", "Halluc_Rate_%"]
        
        for _, row in df.iterrows():
            values = row[metrics].values.tolist()
            values += values[:1]
            angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
            angles += angles[:1]
            
            fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
            ax.fill(angles, values, color='teal', alpha=0.3)
            ax.set_thetagrids(np.degrees(angles[:-1]), metrics)
            ax.set_title(f"Hybrid Profile: {row['Model']}")
            plt.savefig(self.output_dir / f"radar_{row['Model']}.png")
            plt.close()

if __name__ == "__main__":
    # Start the audit
    audit = NLGPerformanceAudit(docs_dir="data")
    audit.run_evaluation()
    audit.plot_heatmap()
    audit.plot_radar()

    print("\n" + "="*80)
    print(" SUMMARY OF METRICS (AVERAGED BY MODEL) ")
    print("="*80)
    
    # Reload and show results in terminal
    df_resumen = pd.read_csv(audit.output_dir / "nlg_evaluation_summary_cleaned.csv")
    print(df_resumen.to_string(index=False, justify='center'))
    print("="*80 + "\n")