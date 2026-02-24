import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# 1. Load structured data
# ──────────────────────────────────────────────

def load_data(path="becas_estructuradas.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt_single(year_data):
    """Build a prompt for summarizing a single year's scholarship data."""
    data_str = json.dumps(year_data, indent=2, ensure_ascii=False)
    return (
        "You are given structured data extracted from an official Spanish government (BOE) "
        "scholarship announcement. Write a clear, concise summary in English that a student "
        "could use to understand the key scholarship details for this academic year. "
        "Cover: eligible programs, scholarship amounts, income thresholds, academic requirements, "
        "application deadlines, and any special provisions (disability, insular supplements, etc.). "
        "Keep it under 300 words.\n\n"
        f"Data:\n{data_str}"
    )


def build_prompt_combined(all_data):
    """Build a prompt for summarizing all years together."""
    data_str = json.dumps(all_data, indent=2, ensure_ascii=False)
    return (
        "You are given structured data extracted from five official Spanish government (BOE) "
        "scholarship announcements, covering academic years 2021-2022 through 2025-2026. "
        "Write a comprehensive summary in English that highlights: "
        "(1) what the scholarships cover and who is eligible, "
        "(2) the main scholarship components and their amounts, "
        "(3) how income thresholds and requirements have evolved over the five years, "
        "(4) application deadlines and any notable changes across years. "
        "Be concise but thorough. Keep it under 500 words.\n\n"
        f"Data:\n{data_str}"
    )


# ──────────────────────────────────────────────
# 2. DeepSeek API (OpenAI-compatible)
# ──────────────────────────────────────────────

def generate_deepseek(prompt, model="deepseek-chat"):
    """Generate summary using DeepSeek API (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )

    # deepseek-reasoner does not support temperature
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }
    if model != "deepseek-reasoner":
        kwargs["temperature"] = 0.7

    start = time.time()
    response = client.chat.completions.create(**kwargs)
    elapsed = time.time() - start

    text = response.choices[0].message.content
    tokens_in = response.usage.prompt_tokens
    tokens_out = response.usage.completion_tokens

    result = {
        "text": text,
        "model": model,
        "time_seconds": round(elapsed, 2),
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
    }

    # Capture reasoning content if available (deepseek-reasoner)
    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
    if reasoning:
        result["reasoning_content"] = reasoning

    return result


# ──────────────────────────────────────────────
# 3. Local model (Hugging Face Transformers)
# ──────────────────────────────────────────────

def generate_local(prompt, model_name="gpt2"):
    """Generate summary using GPT-2 (124M params) locally on MPS/CPU."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"  Loading {model_name} on {device}...")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device)

    # GPT-2 has 1024 token context — truncate prompt and add summary instruction
    prefix = "Summarize the following scholarship data concisely:\n\n"
    max_input = 700  # leave room for generation
    tokens = tokenizer.encode(prefix + prompt)
    if len(tokens) > max_input:
        tokens = tokens[:max_input]
    input_text = tokenizer.decode(tokens)
    inputs = tokenizer(input_text, return_tensors="pt").to(device)
    tokens_in = inputs["input_ids"].shape[1]

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    start = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=300,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.time() - start

    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    tokens_out = len(generated)

    return {
        "text": text,
        "model": model_name,
        "time_seconds": round(elapsed, 2),
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
    }


# ──────────────────────────────────────────────
# 4. Main pipeline
# ──────────────────────────────────────────────

def run_all():
    data = load_data()
    results = {}

    models = [
        ("local", "gpt2"),
        ("deepseek-chat", "deepseek-chat"),
        ("deepseek-reasoner", "deepseek-reasoner"),
    ]

    # --- Per-year summaries ---
    for year_data in data:
        year = year_data["curso_academico"]
        prompt = build_prompt_single(year_data)
        results[year] = {}

        for model_type, model_id in models:
            print(f"\n[{year}] Generating with {model_id}...")
            try:
                if model_type == "local":
                    res = generate_local(prompt, model_id)
                else:
                    res = generate_deepseek(prompt, model_id)
                results[year][model_id] = res
                print(f"  Done in {res['time_seconds']}s ({res['tokens_output']} tokens)")
            except Exception as e:
                print(f"  ERROR: {e}")
                results[year][model_id] = {"error": str(e)}

    # --- Combined summary ---
    combined_prompt = build_prompt_combined(data)
    results["combined"] = {}

    for model_type, model_id in models:
        print(f"\n[COMBINED] Generating with {model_id}...")
        try:
            if model_type == "local":
                res = generate_local(combined_prompt, model_id)
            else:
                res = generate_deepseek(combined_prompt, model_id)
            results["combined"][model_id] = res
            print(f"  Done in {res['time_seconds']}s ({res['tokens_output']} tokens)")
        except Exception as e:
            print(f"  ERROR: {e}")
            results["combined"][model_id] = {"error": str(e)}

    # --- Save results ---
    with open("resumenes_generados.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("\n--- Results saved to resumenes_generados.json ---")

    # --- Print combined summaries for quick review ---
    print("\n" + "=" * 80)
    print("COMBINED SUMMARIES COMPARISON")
    print("=" * 80)
    for model_type, model_id in models:
        entry = results["combined"].get(model_id, {})
        if "text" in entry:
            print(f"\n--- {model_id} ({entry['time_seconds']}s, {entry['tokens_output']} tokens) ---")
            print(entry["text"][:1500])
            print()


if __name__ == "__main__":
    run_all()
