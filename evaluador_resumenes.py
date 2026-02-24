import json
import re
import csv
from pathlib import Path

def load_json(path):
    if not Path(path).exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_numbers(text):
    """Extracts all numbers from text for fact-checking."""
    if not text or not isinstance(text, str):
        return set()
    numbers = re.findall(r'[\d\.,]+', text)
    clean_numbers = set()
    for n in numbers:
        clean = n.replace(".", "").replace(",", "")
        if clean.isdigit():
            clean_numbers.add(clean)
    return clean_numbers

def calculate_repetition_rate(text):
    """Calculates the percentage of repeated words."""
    if not text or len(text.split()) == 0:
        return 0
    words = text.lower().split()
    unique_words = set(words)
    return 1 - (len(unique_words) / len(words))

def run_evaluation():
    print("--- Iniciando Evaluación de Resúmenes (Standard Lib Edition) ---")
    
    # 1. Load data
    structured_data = load_json("becas_estructuradas.json")
    generated_results = load_json("resumenes_generados.json")

    if not structured_data or not generated_results:
        print("Error: No se encontraron los archivos becas_estructuradas.json o resumenes_generados.json")
        return

    facts_by_year = {item["curso_academico"]: item for item in structured_data}
    all_evals = []

    # 2. Iterate through years and models
    for year, models in generated_results.items():
        if year == "combined":
            all_facts_numbers = set()
            for item in structured_data:
                for v in item.values():
                    all_facts_numbers.update(extract_numbers(str(v)))
            target_facts = all_facts_numbers
        else:
            year_facts = facts_by_year.get(year, {})
            target_facts = set()
            for v in year_facts.values():
                target_facts.update(extract_numbers(str(v)))

        for model_name, result in models.items():
            if "error" in result: continue
            
            text = result.get("text", "")
            summary_numbers = extract_numbers(text)
            
            # a) Hallucinations
            hallucinated_nums = summary_numbers - target_facts
            hallucinated_nums = {n for n in hallucinated_nums if len(n) > 1}
            
            # b) Recall
            key_amounts = {n for n in target_facts if len(n) >= 3}
            recalled_nums = summary_numbers.intersection(key_amounts)
            recall_score = (len(recalled_nums) / len(key_amounts) * 100) if key_amounts else 0
            
            repetition = calculate_repetition_rate(text) * 100
            
            eval_entry = {
                "Year": year,
                "Model": model_name,
                "Time_s": result.get("time_seconds", 0),
                "Tokens_Out": result.get("tokens_output", 0),
                "Fact_Recall_Pct": round(recall_score, 2),
                "Hallucinations_Count": len(hallucinated_nums),
                "Repetition_Pct": round(repetition, 2),
                "Word_Count": len(text.split())
            }
            all_evals.append(eval_entry)

    # 3. Save detailed results to CSV
    if all_evals:
        keys = all_evals[0].keys()
        with open("evaluacion_detallada.csv", "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(all_evals)

    # 4. Calculate model comparison manually
    models_stats = {}
    for entry in all_evals:
        m = entry["Model"]
        if m not in models_stats:
            models_stats[m] = {"Time_s": [], "Fact_Recall_Pct": [], "Hallucinations_Count": [], "Repetition_Pct": [], "Word_Count": []}
        for k in models_stats[m].keys():
            models_stats[m][k].append(entry[k])

    comparison_results = []
    for m, stats in models_stats.items():
        summary = {"Model": m}
        for k, v in stats.items():
            summary[k] = round(sum(v) / len(v), 2)
        comparison_results.append(summary)

    if comparison_results:
        keys = comparison_results[0].keys()
        with open("comparativa_modelos.csv", "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(comparison_results)

    print("\n--- Resultados de la Evaluación ---")
    print(f"{'Model':<20} | {'Recall %':<10} | {'Halluc #':<10} | {'Rep %':<10}")
    print("-" * 60)
    for res in comparison_results:
        print(f"{res['Model']:<20} | {res['Fact_Recall_Pct']:<10} | {res['Hallucinations_Count']:<10} | {res['Repetition_Pct']:<10}")
    
    print("\nArchivos generados: 'evaluacion_detallada.csv' y 'comparativa_modelos.csv'")

if __name__ == "__main__":
    run_evaluation()
