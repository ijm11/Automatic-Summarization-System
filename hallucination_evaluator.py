import torch
import json
import re
import os
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Hide TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# We use Vectara's model which is specifically trained to detect hallucinations (when AI lies)
model_name = "vectara/hallucination_evaluation_model"
tokenizer = AutoTokenizer.from_pretrained(model_name, revision="hhem-1.0-open")
model = AutoModelForSequenceClassification.from_pretrained(model_name, revision="hhem-1.0-open")

# Load extraction results and generated summaries
with open('becas_estructuradas.json', 'r', encoding='utf-8') as f:
    becas_data = json.load(f)

with open('resumenes_generados.json', 'r', encoding='utf-8') as f:
    resumenes_data = json.load(f)


def generar_texto_becas(datos):
    """
    To evaluate a summary, the model needs a 'Premise' (the facts).
    This function converts our structured JSON back into a long natural text string.
    """
    texto = f"""Fichero: {datos['fichero']}.
Curso académico: {datos['curso_academico']}.
Programas educativos: {datos['programas_educativos']}
Cuantía renta fija: {datos['cuantia_renta_fija']} euros.
Cuantía residencia: {datos['cuantia_residencia']} euros.
Beca básica: {datos['beca_basica']} euros.
Cuantía variable mínima: {datos['cuantia_variable_minima']} euros.
Excelencia mínima: {datos['excelencia_min']} euros.
Excelencia máxima: {datos['excelencia_max']} euros.
Tramos de excelencia: """
    for tramo in datos['excelencia_tramos']:
        texto += f"Nota media {tramo['nota_media']} recibe {tramo['cuantia_euros']} euros. "
    
    umbrales = datos['umbrales_renta']
    
    # Handle the two different threshold structures (old JSON vs new Table format)
    if 'Umbral 1' in umbrales:
        texto += f"""
Límites Umbral 1: {umbrales['Umbral 1']['un']} (1 miembro), {umbrales['Umbral 1']['dos']} (2 miembros), ...
Límites Umbral 2: {umbrales['Umbral 2']['un']} (1 miembro), {umbrales['Umbral 2']['dos']} (2 miembros), ..."""
    elif 'tabla' in umbrales:
        texto += "\nUmbrales de renta por familia: "
        for item in umbrales['tabla']:
            miembros = item.get('miembros', '?')
            umbral_1 = item.get('umbral_1', '?')
            umbral_2 = item.get('umbral_2', '?')
            umbral_3 = item.get('umbral_3', '?')
            texto += f"{miembros} miembros ({umbral_1}/{umbral_2}/{umbral_3}), "
        texto = texto.rstrip(', ') + "."
    
    # Add requirements, supplements, and deductions
    texto += f"""
Umbrales de patrimonio: Límite urbanas {datos['umbrales_patrimonio']['fincas_urbanas_limite']}.
Requisitos académicos: Créditos completo {datos['requisitos_academicos']['creditos_tiempo_completo']}. 
Suplementos insulares: Básico {datos['suplementos_insulares']['suplemento_insular_basico']}. 
Deducciones de renta: Familia numerosa especial {datos['deducciones_renta']['deduccion_familia_numerosa_especial']}. 
Plazos de solicitud: {datos['plazos_solicitud']['texto_extracto']}"""
    
    return texto

def limpiar_resumen(texto):
    """Removes special markdown characters (like **) that might confuse the evaluator model."""
    if not texto:
        return ""
    texto = texto.replace('*', '')
    texto = re.sub(r'\n+', ' ', texto)
    return texto.strip()

def evaluar_alucinacion(premisa, hipotesis):
    """
    Computes a score from 0 to 1. 
    1.0 means no hallucinations detected (perfect truth). 
    0.0 means the model is likely lying.
    """
    inputs = tokenizer(premisa, hipotesis, return_tensors="pt", truncation=True, max_length=4096)
    with torch.no_grad():
        logits = model(**inputs).logits
        score = torch.sigmoid(logits).squeeze().item()
    return score


# ──────────────────────────────────────────────
# Main Evaluation Loop
# ──────────────────────────────────────────────

anos_disponibles = sorted(set(item['curso_academico'] for item in becas_data))

print("=" * 80)
print("HALLUCINATION EVALUATION RESULTS (VECTARA HHEM)")
print("=" * 80)

for anio_academico in anos_disponibles:
    print(f"\nAcademic Year: {anio_academico}")
    print("-" * 80)
    
    # Find scholarship facts for this year
    datos_becas = next((item for item in becas_data if item['curso_academico'] == anio_academico), None)
    
    if datos_becas is None:
        continue
    
    # Convert facts to text format
    premisa_facts = generar_texto_becas(datos_becas)
    
    # Get the generated summaries for this year
    resumenes_anno = resumenes_data.get(anio_academico, {})
    
    if not resumenes_anno:
        continue
    
    # Evaluate each model's summary
    for model_name in ['gpt2', 'deepseek-chat', 'deepseek-reasoner']:
        gen_text = resumenes_anno.get(model_name, {}).get('text', '')
        if not gen_text:
            continue
            
        cleaned_summary = limpiar_resumen(gen_text)
        halluc_score = evaluar_alucinacion(premisa_facts, cleaned_summary)
        
        print(f"  {model_name.upper():<20}: {halluc_score:.4f}")

print("\n" + "=" * 80)