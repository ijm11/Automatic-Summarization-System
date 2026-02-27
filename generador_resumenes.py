import json
import time
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# We load environment variables from .env (like our API keys)
load_dotenv()

# ──────────────────────────────────────────────
# 1. Data Management Functions
# ──────────────────────────────────────────────

def load_data(path="becas_estructuradas.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt_single(year_data):
    """
    PROMPT GENÉRICO Y HONESTO:
    No se le da una estructura fija. Se pide un resumen profesional en texto plano.
    """
    data_str = json.dumps(year_data, indent=2, ensure_ascii=False)
    return (
        "You are an expert assistant in Spanish education grants. "
        "Based on the following structured data from the official BOE, write a clear "
        "and informative summary in English (200-300 words) for a student interested in applying.\n"
        "The summary should be professional, cover all relevant financial and "
        "requirement details found in the data, and be easy to read.\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY PLAIN TEXT. No markdown, no bold (**), no italics (*), no tables.\n"
        "2. Do not use symbols like '#' or '---'.\n"
        "3. Focus on accuracy and clarity.\n\n"
        f"DATA:\n{data_str}"
    )

def build_prompt_combined(all_data):
    """
    PROMPT DE ANÁLISIS EVOLUTIVO:
    Pide comparar los cambios a lo largo de los años de forma natural.
    """
    data_str = json.dumps(all_data, indent=2, ensure_ascii=False)
    return (
        "Analyze the following data containing scholarship information from 2021 to 2026. "
        "Write a comprehensive report in English explaining how these grants have "
        "changed over the years. Highlight the most significant trends you find in "
        "thresholds, amounts, and requirements.\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY PLAIN TEXT. No markdown, no bold (**), no italics (*).\n"
        "2. Use simple bullet points (-) for lists if necessary.\n\n"
        f"DATA:\n{data_str}"
    )

# ──────────────────────────────────────────────
# 2. DeepSeek API Integration
# ──────────────────────────────────────────────

def generate_deepseek(prompt, model="deepseek-chat"):
    """
    Sends our prompt to the DeepSeek API. 
    We use a low 'temperature' (0.3) so the AI stays focused on facts instead of being too creative.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )

    # We tell the AI how to behave (No markdown, plain text)
    system_msg = "You are a helpful assistant that summarizes technical data into clear plain text without any markdown formatting."

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4096,
    }
    
    # Reasoning model doesn't support 'temperature', so we only set it for the chat model
    if model != "deepseek-reasoner":
        kwargs["temperature"] = 0.3

    start = time.time()
    response = client.chat.completions.create(**kwargs)
    elapsed = time.time() - start

    # We collect some stats about the generation (time, tokens used, etc.)
    result = {
        "text": response.choices[0].message.content,
        "model": model,
        "time_seconds": round(elapsed, 2),
        "tokens_input": response.usage.prompt_tokens,
        "tokens_output": response.usage.completion_tokens,
    }

    # If the model has a "reasoning" step (like DeepSeek-R1), we save that too
    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
    if reasoning:
        result["reasoning_content"] = reasoning

    return result

# ──────────────────────────────────────────────
# 3. Local Model (GPT-2)
# ──────────────────────────────────────────────

def generate_local(prompt, model_name="gpt2"):
    """
    Generates a summary using a model running on our own computer (GPT-2).
    This is slower and less powerful than the API, but works offline!
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    # Use a faster 'MPS' chip on Macs if available, otherwise use CPU
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device)

    prefix = "Summary in plain text:\n\n"
    max_input = 700 
    tokens = tokenizer.encode(prefix + prompt)
    if len(tokens) > max_input:
        tokens = tokens[:max_input]
    input_text = tokenizer.decode(tokens)
    inputs = tokenizer(input_text, return_tensors="pt").to(device)
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    start = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=300,
            temperature=0.3, 
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.time() - start

    # Remove the prompt from the output to get only the new summary
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    
    return {
        "text": text,
        "model": model_name,
        "time_seconds": round(elapsed, 2),
        "tokens_input": inputs["input_ids"].shape[1],
        "tokens_output": len(generated),
    }

# ──────────────────────────────────────────────
# 4. Main Automation Pipeline
# ──────────────────────────────────────────────

def run_all():
    """Loops through all years and generates summaries with all models."""
    data = load_data()
    results = {}

    # List of models we want to compare
    models = [
        ("local", "gpt2"),
        ("deepseek-chat", "deepseek-chat"),
        ("deepseek-reasoner", "deepseek-reasoner"),
    ]

    # --- Phase 1: Yearly Summaries ---
    for year_data in data:
        year = year_data["curso_academico"]
        prompt = build_prompt_single(year_data)
        results[year] = {}

        for model_type, model_id in models:
            print(f"[{year}] -> Generating with {model_id}...")
            try:
                if model_type == "local":
                    res = generate_local(prompt, model_id)
                else:
                    res = generate_deepseek(prompt, model_id)
                results[year][model_id] = res
            except Exception as e:
                print(f"  ERROR in {model_id}: {e}")
                results[year][model_id] = {"error": str(e)}

    # --- Phase 2: Combined Trend Report ---
    combined_prompt = build_prompt_combined(data)
    results["combined"] = {}

    for model_type, model_id in models:
        print(f"[COMBINED] -> Generating with {model_id}...")
        try:
            if model_type == "local":
                res = generate_local(combined_prompt, model_id)
            else:
                res = generate_deepseek(combined_prompt, model_id)
            results["combined"][model_id] = res
        except Exception as e:
            print(f"  ERROR en {model_id}: {e}")
            results["combined"][model_id] = {"error": str(e)}

    # Save all generated text into a single JSON file
    with open("resumenes_generados.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("\n✅ Generation completed! Format biases were avoided.")
    print("Next step: Run the evaluator to check how smart these models really are.")

if __name__ == "__main__":
    run_all()