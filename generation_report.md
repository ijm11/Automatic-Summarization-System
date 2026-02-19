# Language Generation Report

## Overview

After extracting structured scholarship data from the five BOE PDFs into a JSON file (see extraction report), we used three different language models to generate abstractive summaries. The goal was to evaluate how different models handle the task of converting structured data into coherent, human-readable text.

We generated:
- **5 per-year summaries** (one for each academic year, 2021-2026)
- **1 combined summary** (covering all five years together)
- For each, we ran **3 models**, giving us **18 total summaries**

## Models Used

| Model | Type | Parameters | Description |
|---|---|---|---|
| **GPT-2** | Local (HuggingFace) | 124M | OpenAI's base language model (2019). Not instruction-tuned — included as a baseline to show the difference between base models and modern instruction-following models. |
| **DeepSeek-Chat** (V3.2) | API | Unknown (closed) | DeepSeek's latest general-purpose chat model. Fast, instruction-tuned, supports long context (128K tokens). |
| **DeepSeek-Reasoner** (V3.2) | API | Unknown (closed) | Same architecture as DeepSeek-Chat but with chain-of-thought reasoning enabled. The model "thinks" internally before generating the final answer. |

## Pipeline Architecture

```
becas_estructuradas.json
        |
        v
  build_prompt()  ──> Structured JSON + task instruction
        |
        ├──> GPT-2 (local, MPS)     ──> summary text
        ├──> DeepSeek-Chat (API)     ──> summary text
        └──> DeepSeek-Reasoner (API) ──> reasoning + summary text
        |
        v
  resumenes_generados.json  (all results + metadata)
```

The prompt asks the model to produce a concise English summary covering eligible programs, scholarship amounts, income thresholds, academic requirements, deadlines, and special provisions. For per-year summaries, the target is under 300 words; for the combined summary, under 500 words.

## Results

### Performance Metrics

| Model | Avg Time (per-year) | Avg Output Tokens | Input Handling |
|---|---|---|---|
| GPT-2 | ~26s | 300 (max) | Truncated to 700 tokens (1024 context limit) |
| DeepSeek-Chat | ~11s | 478 | Full JSON input (~1,900 tokens per year) |
| DeepSeek-Reasoner | ~16s | 722 | Full JSON input (~1,900 tokens per year) |

For the combined summary (all 5 years, ~9,100 input tokens):

| Model | Time | Output Tokens |
|---|---|---|
| GPT-2 | 26.2s | 300 |
| DeepSeek-Chat | 16.7s | 761 |
| DeepSeek-Reasoner | 19.9s | 960 |

### Quality Comparison

**GPT-2 (Baseline):**
GPT-2 completely fails at the summarization task. Being a base model from 2019 with no instruction tuning, it simply continues the input text rather than summarizing it. The output is a garbled repetition of fragments from the source data, sometimes with hallucinated text mixed in (e.g., inventing names, repeating PDF validation codes). It also cannot process the full input since its context window is limited to 1,024 tokens, so most of the structured data is lost. This result clearly illustrates why instruction-tuned models are necessary for practical NLG tasks.

**DeepSeek-Chat (V3.2):**
Produces well-structured, accurate summaries. It correctly identifies the key scholarship components, lists actual euro amounts from the data, groups information logically (eligible programs, amounts, thresholds, deadlines), and uses formatting (bold text, bullet points) for readability. The combined summary successfully highlights trends across years, such as the residence allowance increase from 1,600 to 2,700 euros. Summaries are concise and stay close to the requested word count. Occasionally it hits the token limit and truncates mid-sentence.

**DeepSeek-Reasoner (V3.2):**
Generates slightly longer, more thorough summaries than Chat. The chain-of-thought reasoning (visible in the saved JSON as `reasoning_content`) helps the model plan the structure before writing. The output tends to be better organized: it consistently covers all requested topics, provides more context for each data point, and makes clearer cross-year comparisons in the combined summary. The trade-off is a ~45% increase in response time compared to Chat. The reasoning process typically consists of 1,000-1,800 characters of internal planning.

### Example: Combined Summary (DeepSeek-Reasoner)

> Based on the Spanish government scholarship announcements for academic years 2021-2022 to 2025-2026, here is a comprehensive summary.
>
> **1. Coverage & Eligibility:** The scholarships support a wide range of post-compulsory and higher education. Eligible programs include: Baccalaureate, intermediate and advanced Vocational Training, professional and advanced Arts and Sports studies, advanced Religious studies, official Language school courses, access courses, and Basic Vocational Training. For university studies, they cover official Bachelor's and Master's degrees, access courses for over-25s, and specific complementary credits. Scholarships are not awarded for PhDs, specializations, or university-specific degrees.
>
> **2. Main Components & Amounts:** The scholarship is comprised of several fixed and variable components: a basic grant (€300) and a fixed income-based grant (€1,700) remained constant for all five years. The Residence Grant saw a significant increase: €1,600 (2021-2023), rising to €2,500 (2023-2025), then to €2,700 (2025-2026). A variable amount (minimum €60) is calculated based on family income. Excellence supplements range from €50 (GPA 8.0-8.49) to €125 (GPA 9.5+).

## Conclusions

1. **Base models are unsuitable for structured summarization.** GPT-2 (124M params, no instruction tuning) cannot follow instructions or produce coherent summaries from structured data. It merely generates continuations of the input tokens.

2. **Instruction-tuned models handle the task well.** Both DeepSeek-Chat and DeepSeek-Reasoner produce accurate, well-organized summaries that correctly reference specific data points from the JSON input.

3. **Reasoning mode adds marginal quality.** DeepSeek-Reasoner produces slightly more structured and complete outputs, at the cost of ~45% more latency. For a task of this complexity, the reasoning overhead may not be strictly necessary, but it does help with multi-year comparisons.

4. **Context window matters.** GPT-2's 1,024-token limit means it can only see a fraction of the data. The DeepSeek models (128K context) can process the full JSON for all five years simultaneously, enabling genuine cross-year analysis.

5. **The summarization pipeline is simple and effective.** Converting structured JSON to a natural language summary requires only a clear prompt and a capable instruction-tuned model. No fine-tuning or complex architectures are needed.
