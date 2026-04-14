# LearnPilot — Model Selection Report (Phase 1)

**Course:** CSC 603/803 — Generative AI (Capstone)  
**Project:** LearnPilot — An AI-Powered Adaptive Learning Assistant  
**Document purpose:** Record our choice of large language model, runtime, and rationale for the team repository and Phase 1 submission.  
**Last updated:** April 14, 2026  

---

## 1. Executive summary

LearnPilot will use a **local, open-weight instruct model** rather than a commercial inference API. After comparing hardware constraints, educational goals, and licensing, we will standardize on **Qwen2.5-14B-Instruct** served in a **quantized (approximately 4-bit) MLX build** on **Apple Silicon** (development lead machine: MacBook Pro with M4 Pro and 24 GB unified memory). Model weights will **not** be stored in Git; they will be downloaded to a local cache on whichever machine runs the backend. Team members who work only on the frontend will call our **HTTP API** and do not need a local copy of the weights.

---

## 2. Project requirements (constraints we optimized for)

From our capstone proposal and team decisions, the model layer must support:

- **Two learning modes:** (1) concept-first learning and (2) learning by deconstruction (reverse engineering), using **prompt engineering** and structured outputs.
- **Subject matter:** programming, algorithms, mathematics, and general explanatory text — so we need strong **instruction following**, **clear language**, and **step-by-step** explanations.
- **No paid token API for core inference:** We align with course practice (e.g. using pretrained models via Hugging Face–style workflows) to avoid per-request billing and to retain **control** over prompts, decoding parameters, and data handling.
- **Privacy and reproducibility:** Running inference locally keeps user prompts and pasted code on **our** hardware when desired; we can **pin** a specific model revision for consistent grading and demos.
- **Team workflow:** Backend hosts the model; frontend consumes a **REST API**. Repository stores **code and configuration only**, not multi-gigabyte checkpoints.

---

## 3. Hardware context (development baseline)

Primary on-device target for the backend developer:

- **Apple M4 Pro**, **24 GB unified memory**, macOS.

Implication: we cannot treat **very large** dense models (e.g. tens of billions of parameters at full precision) as the default **laptop** configuration. We chose a **14-billion-parameter instruct model** with **aggressive quantization** so weights, runtime, and a reasonable **context window** fit alongside the operating system and application memory.

---

## 4. Selected model and runtime

| Item | Choice |
|------|--------|
| **Base model** | **Qwen2.5-14B-Instruct** (Alibaba Qwen family, instruction-tuned for chat and task following) |
| **Quantization** | **~4-bit** (or equivalent) to fit 24 GB unified memory |
| **Runtime** | **MLX** via **`mlx-lm`** (Apple’s framework for efficient inference on Apple Silicon) |
| **Weight distribution** | **Hugging Face Hub**, typically under community MLX conversions (e.g. **`mlx-community`** organization repositories — exact repo name and revision to be pinned in `README` or config when implementation begins) |

### 4.1 What each piece means

- **Qwen2.5-14B-Instruct:** The **model** (learned parameters and chat-tuned behavior). Alibaba releases Qwen under its **license**; we must comply with terms for research and any future product use.
- **Quantization:** Compresses weights to reduce **memory**; modest quality tradeoffs for large gains in feasibility on consumer hardware.
- **MLX / mlx-lm:** The **inference stack** on Mac — analogous to using CUDA-backed tools on Linux; it is not the model owner, only the **engine** that executes the converted checkpoint.
- **Hugging Face:** The **distribution platform** where we obtain the **MLX-packaged** checkpoint. Alternatives exist (official vendor pages, Ollama, etc.), but Hugging Face is our planned **default** for versioning and documentation links.

---

## 5. Rationale (why this model and stack)

1. **Teaching and language quality:** At **14B** parameters, instruct-tuned models generally produce **richer explanations** and more stable **structure** (steps, headings, analogies) than smaller models, which matters for LearnPilot’s pedagogical modes.
2. **Code and reasoning:** The Qwen2.5 line is widely used for **code** and **analytical** tasks; that supports programming and algorithms content in our scope.
3. **Fits the Mac:** **14B + 4-bit MLX** is a realistic **maximum practical** choice for **24 GB** unified memory while leaving headroom for the OS, API server, and context.
4. **Alignment with course goals:** Uses **pretrained open-weight** models and local inference, consistent with in-class activities (e.g. Hugging Face Transformers / local workflows) without depending on proprietary chat APIs for core generation.
5. **Scaling path:** The application can later target a **remote GPU** (vLLM, cloud VM, etc.) with a **larger** checkpoint using the same **HTTP API** contract; only the deployment target changes.

---

## 6. Alternatives considered

| Alternative | Why not chosen as default (for Phase 1 on 24 GB Mac) |
|-------------|------------------------------------------------------|
| **OpenAI / Anthropic / Google APIs** | Strong convenience and quality, but **per-token cost**, **external dependency**, and **data leaves our machine** — conflicts with our local-first capstone direction. |
| **Meta Llama (e.g. 8B instruct)** | Excellent ecosystem and documentation; **8B** is easier on memory but offers **less headroom** for long, nuanced teaching at the same RAM budget as **14B quantized Qwen**. Llama remains a **backup** option if we standardize on Meta licensing or team preference. |
| **Larger local models (32B–70B+)** | **Exceed practical unified-memory limits** on the primary dev laptop without remote hardware or extreme tradeoffs. |
| **GGUF + llama.cpp / Ollama** | Viable for teammates on **non-Mac** systems or as a **second** runtime; our **lead backend** target is **MLX** on Apple Silicon. |

---

## 7. Repository, GitHub, and team workflow

- **GitHub stores:** application source, API specification, prompts, frontend assets, dependency manifests, and **this report**.
- **GitHub does not store:** full model weights (multi-gigabyte files are impractical for git and unnecessary).
- **Backend developer:** downloads the pinned MLX model once (or on first app start) into the **local Hugging Face / MLX cache**.
- **Frontend developers:** run the UI and configure **`API_BASE_URL`** (or equivalent) to the backend host (e.g. teammate’s machine on the same network, or a tunnel for remote demos).
- **Professor / reviewers:** can verify **design and rationale** from this document and code; running the full stack requires **one machine** with the weights downloaded (or a recorded demo).

---

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| **Hallucinations or incorrect teaching content** | Structured prompts, mode-specific templates, optional “uncertainty” instructions, and human review in evaluation (per proposal). |
| **Laptop offline → app unavailable for teammates** | Document expectation for Phase 1; plan optional **deployed** backend (lab server or cloud) before final demo if required. |
| **License / use restrictions** | Read and comply with **Qwen2.5** license; cite model in report and UI as required. |
| **Teammate without Mac** | Provide **API contract** and optional **Ollama/GGUF** path or shared server so they are not blocked. |

---

## 9. Phase 2 (implementation) next steps

1. Pin **exact** Hugging Face repository ID and **revision hash** for the MLX checkpoint.  
2. Implement **FastAPI** (or Flask) backend: load model once at startup, expose endpoints for **concept-first** and **deconstruction** modes.  
3. Document **environment setup** (`python` version, `mlx-lm`, first-run download size, approximate disk usage).  
4. Add **`.gitignore`** rules for caches and local secrets; never commit tokens or API keys.  

---

## 10. References (for the course packet)

- Hugging Face — Transformers and Hub documentation: [https://huggingface.co/docs](https://huggingface.co/docs)  
- Qwen2.5 model family (verify current license and model card on the Hub): search **Qwen2.5-14B-Instruct** on [https://huggingface.co/models](https://huggingface.co/models)  
- Apple MLX: [https://github.com/ml-explore/mlx](https://github.com/ml-explore/mlx)  
- Capstone proposal on file: `CSC603_Capstone_Proposal.pdf` (project goals, modes, timeline)  

---

*This report was prepared for Phase 1 submission and team onboarding. The exact Hub path and revision will be finalized when the backend scaffold is merged.*
