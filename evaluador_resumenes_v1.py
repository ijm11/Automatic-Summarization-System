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
from rouge_score import rouge_scorer

# Intentamos importar las librerías de métricas de texto. 
# Si no las tienes, el script seguirá funcionando pero omitirá esas columnas.
try:
    from rouge_score import rouge_scorer
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    HAS_NLP_METRICS = True
except ImportError:
    HAS_NLP_METRICS = False

class NLGPerformanceAudit:
    """
    Marco de evaluación integral para sistemas de Generación de Lenguaje Natural (NLG).
    Analiza la fidelidad de datos (Data-to-Text), alucinaciones, eficiencia 
    y similitud lingüística (ROUGE/BLEU).
    """

    def __init__(self, data_path="becas_estructuradas.json", gen_path="resumenes_generados.json"):
        self.data_path = data_path
        self.gen_path = gen_path
        self.results = []
        
        # DEFINICIÓN DE CARPETA DE SALIDA
        # Centralizamos todos los gráficos y reportes en un solo directorio
        self.output_dir = Path("resultados_evaluacion")
        self.output_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # CARGA DE DATOS
    # ------------------------------------------------------------------
    def _load_data(self):
        """Carga la base de conocimientos y los textos generados por los LLMs."""
        if not Path(self.data_path).exists() or not Path(self.gen_path).exists():
            print("❌ Input files not found.")
            return False

        with open(self.data_path, "r", encoding="utf-8") as f:
            self.ground_truth = json.load(f)
        with open(self.gen_path, "r", encoding="utf-8") as f:
            self.generated = json.load(f)
        return True

    # ------------------------------------------------------------------
    # EXTRACCIÓN NUMÉRICA (Auditoría de Veracidad)
    # ------------------------------------------------------------------
    def _extract_numbers(self, obj):
        """Extrae cifras para detectar alucinaciones numéricas (untruthful content)."""
        numbers = set()
        if isinstance(obj, (dict, list)):
            items = obj.values() if isinstance(obj, dict) else obj
            for i in items:
                numbers.update(self._extract_numbers(i))
        elif isinstance(obj, (int, float, str)):
            matches = re.findall(r"\d+(?:[\.,]\d+)?", str(obj))
            for m in matches:
                clean = m.replace(".", "").replace(",", "")
                if len(clean) >= 2: 
                    numbers.add(clean)
        return numbers

    # ------------------------------------------------------------------
    # BUCLE DE EVALUACIÓN PRINCIPAL
    # ------------------------------------------------------------------
    def run_evaluation(self):
        """
        Ejecuta el análisis de métricas D2T e incluye ROUGE/BLEU.
        """
        import nltk
        from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
        
        # Descarga automática de los paquetes de datos necesarios
        try:
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True) # <--- Esta es la que te falta
        except Exception as e:
            print(f"⚠️ Aviso al descargar recursos NLTK: {e}")

        if not self._load_data():
            return
        # Mapeo de la verdad de campo por año
        facts_by_year = {item["curso_academico"]: item for item in self.ground_truth}
        
        # Configuramos el calculador de ROUGE
        if HAS_NLP_METRICS:
            r_scorer = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
            smooth_func = SmoothingFunction().method1

        for year, models in self.generated.items():
            # Datos de referencia del JSON
            ref_data = self.ground_truth if year == "combined" else facts_by_year.get(year)
            if ref_data is None: continue

            ref_numbers = self._extract_numbers(ref_data)
            
            # Buscamos el texto del modelo 'reasoner' para usarlo como referencia lingüística
            reference_text = models.get("deepseek-reasoner", {}).get("text", "")

            for model_name, data in models.items():
                if "error" in data: continue

                summary_text = data["text"]
                sum_numbers = self._extract_numbers(summary_text)

                # 1. RECALL (Fidelidad): ¿Qué % de los datos del BOE capturó el modelo?
                hits = sum_numbers.intersection(ref_numbers)
                recall = (len(hits) / len(ref_numbers) * 100 if ref_numbers else 0)

                # 2. HALLUCINATION RATE: % de números inventados sobre el total en el resumen.
                hallucinations = sum_numbers - ref_numbers
                halluc_rate = (len(hallucinations) / len(sum_numbers) * 100 if sum_numbers else 0)

                # 3. REDUNDANCY: Detecta bucles y falta de variedad léxica.
                words_list = summary_text.lower().split()
                repetition = ((1 - len(set(words_list)) / len(words_list)) * 100 if words_list else 0)

                # 4. MÉTRICAS LINGÜÍSTICAS (NLP)
                rouge_score = 0
                bleu_score = 0
                
                if HAS_NLP_METRICS and reference_text:
                    # Si evaluamos el propio modelo de referencia, es un 100% perfecto
                    if model_name == "deepseek-reasoner":
                        rouge_score = 100.0
                        bleu_score = 100.0
                    else:
                        # ROUGE-L: Mide la estructura y coherencia gramatical
                        rouge_score = r_scorer.score(reference_text, summary_text)['rougeL'].fmeasure * 100
                        
                        # BLEU: Mide la precisión de n-gramas con tokenización profesional
                        ref_tokens = nltk.word_tokenize(reference_text.lower())
                        gen_tokens = nltk.word_tokenize(summary_text.lower())
                        bleu_score = sentence_bleu([ref_tokens], gen_tokens, smoothing_function=smooth_func) * 100

                self.results.append({
                    "Year": year,
                    "Model": model_name,
                    "Recall_%": round(recall, 2),
                    "Halluc_Rate_%": round(halluc_rate, 2),
                    "Repetition_%": round(repetition, 2),
                    "ROUGE_L_%": round(rouge_score, 2),
                    "BLEU_%": round(bleu_score, 2),
                    "Latency_s": round(data.get("time_seconds", 0), 2)
                })

        self._generate_outputs()
    # ------------------------------------------------------------------
    # GENERACIÓN DE SALIDAS Y GRÁFICOS
    # ------------------------------------------------------------------
    def _generate_outputs(self):
        """Genera reportes y el panel de visualización principal."""
        df = pd.DataFrame(self.results)
        df_avg = df.groupby("Model").mean(numeric_only=True).reset_index()

        df.to_csv(self.output_dir / "nlg_evaluation_detailed.csv", index=False)
        df_avg.to_csv(self.output_dir / "nlg_evaluation_summary.csv", index=False)

        sns.set_theme(style="whitegrid")
        fig, axes = plt.subplots(2, 3, figsize=(18, 10)) # Ampliamos a 2x3 para nuevas métricas
        fig.suptitle("Panel de Control de Evaluación NLG (D2T & T2T)", fontsize=20)

        metrics = [
            ("Recall_%", "Fidelidad (Recall %)"), 
            ("Halluc_Rate_%", "Tasa Alucinación (%)"),
            ("Repetition_%", "Redundancia (%)"),
            ("ROUGE_L_%", "Similitud ROUGE-L (%)"),
            ("BLEU_%", "Puntuación BLEU (%)"),
            ("Latency_s", "Latencia (seg)")
        ]

        for i, (col, title) in enumerate(metrics):
            ax = axes[i//3, i%3]
            sns.barplot(x="Model", y=col, data=df_avg, ax=ax, hue="Model", legend=False)
            ax.set_title(title)
            ax.tick_params(axis='x', rotation=45)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(self.output_dir / "nlg_dashboard_completo.png")
        plt.close()

        print(f"✅ Evaluación finalizada. Carpeta de resultados: {self.output_dir}")

    def plot_heatmap(self):
        """Genera un mapa de calor para comparar todos los modelos de un vistazo."""
        df = pd.read_csv(self.output_dir / "nlg_evaluation_summary.csv").set_index("Model")
        plt.figure(figsize=(12, 6))
        sns.heatmap(df, annot=True, fmt=".2f", cmap="YlGnBu", linewidths=0.5)
        plt.title("Heatmap: Comparativa de Rendimiento Global")
        plt.tight_layout()
        plt.savefig(self.output_dir / "nlg_heatmap_final.png")
        plt.close()

    def plot_radar(self):
        """Genera gráficos de araña para visualizar el perfil de cada modelo."""
        df = pd.read_csv(self.output_dir / "nlg_evaluation_summary.csv")
        # Seleccionamos las métricas clave para el radar
        metrics = ["Recall_%", "Halluc_Rate_%", "Repetition_%", "ROUGE_L_%"]

        for _, row in df.iterrows():
            values = row[metrics].values.tolist()
            values += values[:1]
            angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
            angles += angles[:1]

            fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
            ax.plot(angles, values, color='teal', linewidth=2)
            ax.fill(angles, values, color='teal', alpha=0.25)
            ax.set_thetagrids(np.degrees(angles[:-1]), metrics)
            ax.set_title(f"Perfil de Modelo: {row['Model']}", y=1.1)
            plt.savefig(self.output_dir / f"radar_{row['Model']}.png")
            plt.close()

if __name__ == "__main__":
    audit = NLGPerformanceAudit()
    audit.run_evaluation()
    audit.plot_heatmap()
    audit.plot_radar()