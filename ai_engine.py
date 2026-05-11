"""
ai_engine.py — LearnPilot AI Engine v2
Multi-agent RAG pipeline following HW3 patterns from class.

Agents:
  Agent 1 — Keyword Extractor
            Converts any natural language question into a clean topic
            so RAG can search effectively. Handles any language/phrasing.

  Agent 2 — Explanation Generator
            Three learning modes:
              - Concept-First Learning (default)
              - Reverse Engineering
              - Visual Learning
            Uses Chain of Thought reasoning before generating response.
            Grounded by RAG context but thinks independently.

Design: provider-agnostic — swap model via .env MODEL_ID
"""

import os
import re
import logging
import urllib.parse
from groq import Groq
from dotenv import load_dotenv
from rag_service import retrieve_context
from pdf_service import get_pdf_context

load_dotenv()
logger = logging.getLogger("LearnPilot")

# ─── Provider Config ──────────────────────────────────────────────────────────
# Groq free models:
#   llama-3.3-70b-versatile  ← best quality (recommended)
#   llama3-8b-8192           ← fastest
MODEL_ID     = os.getenv("MODEL_ID", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

client = Groq(api_key=GROQ_API_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — KEYWORD EXTRACTOR
# Converts natural language questions into clean searchable topics.
# Pattern: same as HW3's keyword_extraction_agent
# ══════════════════════════════════════════════════════════════════════════════

KEYWORD_EXTRACTOR_SYSTEM = """You are a topic extraction assistant.
Your only job is to extract the core educational topic from a user's question or input.

Rules:
- Return ONLY the core topic — nothing else. No explanation, no punctuation, no extra words.
- If the input is already a clean topic (e.g. "Binary Search"), return it as-is.
- If the input is a question (e.g. "Why do we need pointers in C?"), extract the topic (e.g. "C pointers").
- If the input is vague (e.g. "I'm confused about that thing in biology"), return your best guess at the topic.
- Keep it short — 1 to 5 words maximum.
- Never return a full sentence.

Examples:
  Input:  "I don't understand why we need pointers in C"
  Output: C pointers

  Input:  "can you explain how the water cycle works"
  Output: water cycle

  Input:  "what happened during the French Revolution"
  Output: French Revolution

  Input:  "Binary Search"
  Output: Binary Search

  Input:  "how does photosynthesis work in plants"
  Output: photosynthesis
"""


def extract_keyword(user_input: str) -> str:
    """
    Agent 1 — Keyword Extractor.
    Takes any user input (question, statement, topic) and returns
    a clean 1-5 word topic string for RAG to search on.

    Falls back to original input if extraction fails.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": KEYWORD_EXTRACTOR_SYSTEM},
                {"role": "user",   "content": user_input},
            ],
            temperature=0.0,    # no randomness — we want consistent extraction
            max_tokens=20,      # topic should be very short
        )
        extracted = response.choices[0].message.content.strip()

        # Safety check — if model returned a long sentence, fall back
        if len(extracted.split()) > 6:
            logger.warning(f"[Agent1] Extraction too long, using original: '{user_input}'")
            return user_input

        logger.info(f"[Agent1] '{user_input}' → '{extracted}'")
        return extracted

    except Exception as e:
        logger.warning(f"[Agent1] Keyword extraction failed: {e} — using original input")
        return user_input


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — SYSTEM PROMPTS (one per learning mode)
# All use Chain of Thought — model reasons before answering.
# ══════════════════════════════════════════════════════════════════════════════

CONCEPT_FIRST_SYSTEM = """You are LearnPilot, an expert educational AI assistant.
You teach ANY subject — science, history, math, programming, languages, arts, and more.
Your method: Concept-First Learning — start from fundamentals, build up gradually.

Generate your response using EXACTLY these section headers:

## Concept
Write the core concept in plain language. Use an analogy to something familiar if it helps.
Be thorough — cover the full idea, not just a definition.

## Explanation
Go deep. Explain how and why it works, the underlying mechanics, the key relationships.
Connect it to things the learner already knows. The more detail the better.

## Example
Give ONE concrete, subject-appropriate example:
- Science/Biology → real experiment, organism, or natural process with actual details
- History → real event, person, or case study with specific facts
- Math/Physics → fully worked numerical problem showing every step
- Programming/CS → working code with inline comments explaining each line
Write the example directly — do not explain what type of example you are giving.

## Complexity
Go deeper into one advanced aspect, edge case, or nuance.
This shows the learner there is more beneath the surface.

## Real World Applications
Give 3-5 numbered real-world applications. Be specific:
- Name actual companies, technologies, products, or research fields
- Explain exactly HOW this concept is applied in each case

CRITICAL RULES:
- Write content IMMEDIATELY after each header — no preamble, no meta-commentary
- For code: ONLY use markdown code blocks for programming/CS topics
- Never write "Here is..." or "I will now explain..." — write the content directly
- Use ALL available tokens to make explanations rich and detailed
- Never skip a section
"""

REVERSE_ENGINEERING_SYSTEM = """You are LearnPilot, an expert educational AI assistant.
You teach ANY subject — science, history, math, programming, languages, arts, and more.
Your method: Reverse Engineering (Learning by Deconstruction) — start with the complete
picture, then systematically break it apart so the learner understands every piece.

Generate your response using EXACTLY these section headers:

## Complete Solution
Present the FULL solution, system, event, or example upfront — no build-up:
- Programming/CS → complete working code with inline annotations
- Biology/Science → complete process or system description with all steps
- History → the full sequence of events or complete case study
- Math → fully worked solution showing every step and intermediate result
Never use code for non-programming topics.

## Component Breakdown
Break the solution into numbered components. For each one:
- Name it clearly
- Show or describe that specific piece in isolation
- Explain precisely what it does and why it exists
Be thorough — every meaningful part deserves its own entry.

## Step-by-Step Explanation
Walk through the complete flow from start to finish.
Explain WHY each step is necessary, not just what it does.
Show how each component connects to the next.

## Concept Connections
Identify the underlying principles, theories, and named concepts at play.
For each concept: name it, explain it, and show exactly where it appears in the solution.
(e.g. "This uses divide-and-conquer because...", "This reflects Newton's Third Law because...")

## Real World Applications
Give 3-5 numbered real-world applications. Be specific:
- Name actual companies, technologies, products, or research fields
- Explain exactly HOW this concept or system is used in each case

CRITICAL RULES:
- ALWAYS start with the COMPLETE solution — never build up gradually
- For code: ONLY use markdown code blocks for programming/CS topics
- Write content IMMEDIATELY after each header — no preamble
- Use ALL available tokens for rich, detailed explanations
- Never skip a section
"""

VISUAL_SYSTEM = """You are LearnPilot, an expert educational AI assistant.
You teach ANY subject — science, history, math, programming, languages, arts, and more.
Your method: Visual Learning — explain primarily through diagrams and visual representations.

Choose the best visual format for the topic:
- FLOW/PROCESS: algorithms, cycles, biological processes → Mermaid flowchart
- TIMELINE: historical events, sequences → Mermaid timeline
- COMPARISON: comparing concepts side by side → markdown table
- HIERARCHY: taxonomies, org structures → Mermaid graph TD
- MIND MAP: connected concepts → Mermaid mindmap

Generate your response using EXACTLY these section headers:

## Visual Overview
Create the primary visual using Mermaid. Follow these STRICT rules or the diagram breaks:
1. Start with: graph TD
2. Each node on its OWN LINE with 4 spaces indent
3. Arrows: --> (never -->|label|>)
4. Labels in square brackets: A[Short Label]
5. Keep labels 1-3 words maximum
6. Maximum 8 nodes
7. Multi-word labels: A["Two\nWords"] using \n for line break

CORRECT:
```mermaid
graph TD
    A[Start] --> B[Step One]
    B --> C[Step Two]
    C --> D[End]
```
WRONG (never all on one line):
```mermaid
graph TD A[Start] --> B[Step] --> C[End]
```

## What You're Looking At
Explain the visual in 4-6 sentences. Walk through it systematically.
Point out the most important nodes and connections. Explain the overall flow or structure.

## Key Components
Numbered list of every element in the diagram.
Each item: name + thorough 2-3 sentence explanation of its role and significance.
Cover every node — leave nothing unexplained.

## Real World Applications
Give 3-5 numbered real-world applications. Be specific:
- Name actual companies, technologies, products, or research fields
- Explain exactly HOW this concept is applied in each case

CRITICAL RULES:
- Visual MUST be first
- Each Mermaid node on its own line — never all on one line
- Write content IMMEDIATELY after headers — no preamble
- Use ALL available tokens for rich explanations
- Never skip a section
"""


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS — inject RAG context into user message
# ══════════════════════════════════════════════════════════════════════════════

def _context_block(context: str, is_pdf: bool = False) -> str:
    """Format context for injection. PDF context is treated as authoritative source."""
    if not context:
        return ""
    if is_pdf:
        # PDF context is the PRIMARY source — LLM must teach from it
        return (
            f"IMPORTANT: The student has uploaded a textbook. "
            f"You MUST base your entire explanation on the following textbook content. "
            f"Do NOT use generic examples — use the specific concepts, equations, "
            f"examples, and terminology from this text.\n\n"
            f"{context}\n\n"
            f"---\n\n"
            f"Teach the concepts from the above textbook content. "
            f"Reference specific details, equations, and examples from the text. "
            f"If the text mentions specific values, formulas, or cases, use them.\n\n"
        )
    return (
        f"Here is relevant background information to help ground your response:\n\n"
        f"{context}\n\n"
        f"---\n\n"
        f"Use the above context where helpful, but also rely on your own knowledge.\n\n"
    )


def build_concept_first_prompt(topic: str, original_input: str,
                                code_snippet: str = None, context: str = "", is_pdf: bool = False) -> str:
    prompt = _context_block(context, is_pdf)
    # Use original input so the model sees what the learner actually asked
    prompt += f"The learner asked: \"{original_input}\"\nCore topic: {topic}"
    if code_snippet:
        prompt += f"\n\nRelated code provided:\n```\n{code_snippet}\n```"
    prompt += "\n\nPlease follow the Concept-First Learning structure exactly."
    return prompt


def build_reverse_engineering_prompt(topic: str, original_input: str,
                                      code_snippet: str = None, context: str = "", is_pdf: bool = False) -> str:
    prompt = _context_block(context, is_pdf)
    prompt += f"The learner asked: \"{original_input}\"\nCore topic: {topic}"
    if code_snippet:
        prompt += (
            f"\n\nDeconstruct this specific code/content:\n```\n{code_snippet}\n```"
        )
    else:
        prompt += (
            f"\n\nCreate a complete, realistic example for this topic first, "
            f"then deconstruct it step by step."
        )
    prompt += "\n\nPlease follow the Reverse Engineering structure exactly."
    return prompt


def build_visual_prompt(topic: str, original_input: str,
                         context: str = "", is_pdf: bool = False) -> str:
    prompt = _context_block(context, is_pdf)
    prompt += f"The learner asked: \"{original_input}\"\nCore topic: {topic}"
    prompt += (
        "\n\nCreate a visual explanation of this topic. "
        "Choose the most appropriate visual format (Mermaid diagram, ASCII, table, etc.) "
        "based on the nature of the topic. "
        "Please follow the Visual Learning structure exactly."
    )
    return prompt


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE PARSER
# Extracts structured sections from raw LLM markdown output
# ══════════════════════════════════════════════════════════════════════════════

def parse_response(raw_text: str, mode: str) -> dict:
    """
    Parse raw LLM markdown into structured fields matching LearningResponse schema.
    Handles all three modes. Falls back gracefully if model didn't follow structure.
    """
    section_pattern = re.compile(r"##\s+(.+?)\n(.*?)(?=\n##\s|\Z)", re.DOTALL)
    sections = {
        m.group(1).strip(): m.group(2).strip()
        for m in section_pattern.finditer(raw_text)
    }

    steps = []
    exercise = ""
    full_explanation = ""

    if mode == "Concept-First Learning":
        concept     = sections.get("Concept", "")
        explanation = sections.get("Explanation", "")
        example     = sections.get("Example", "")
        complexity  = sections.get("Complexity", "")
        practice    = sections.get("Practice Question", "")
        real_world_c = sections.get("Real World Applications", "")

        full_explanation = f"{concept}\n\n{explanation}" if concept else explanation

        if concept:    steps.append(f"**Concept:** {concept[:120]}...")
        if example:    steps.append("**Example provided** — see full explanation")
        if complexity: steps.append(f"**Advanced:** {complexity[:120]}...")

        exercise = ""

    elif mode == "Reverse Engineering":
        solution    = sections.get("Complete Solution", "")
        breakdown   = sections.get("Component Breakdown", "")
        step_exp    = sections.get("Step-by-Step Explanation", "")
        concepts    = sections.get("Concept Connections", "")
        reconstruct = sections.get("Reconstruction Exercise", "")

        full_explanation = f"{solution}\n\n{breakdown}" if solution else breakdown

        if solution:   steps.append("**Complete solution** presented upfront")
        if breakdown:  steps.append("**Components** identified and explained")
        if step_exp:   steps.append("**Execution flow** walked through")
        if concepts:   steps.append(f"**Concepts:** {concepts[:120]}...")

        exercise = ""

    elif mode == "Visual Learning":
        visual      = sections.get("Visual Overview", "")
        what        = sections.get("What You're Looking At", "")
        components  = sections.get("Key Components", "")
        real_world  = sections.get("Real World Applications", "")

        full_explanation = f"{visual}\n\n{what}" if visual else what

        if visual:      steps.append("**Visual diagram** — see above")
        if components:  steps.append(f"**Components:** {components[:120]}...")
        if real_world:  steps.append(f"**Real world:** {real_world[:120]}...")

        exercise = ""

    # Universal fallback
    if not full_explanation:
        full_explanation = raw_text
    if not steps:
        steps = ["AI response generated — see explanation above."]
    if not exercise:
        exercise = ""

    real_world_section = sections.get("Real World Applications", "")

    return {
        "mode":        mode,
        "explanation": full_explanation,
        "raw":         raw_text,
        "steps":       steps,
        "exercise":    exercise,
        "real_world":  real_world_section,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AIEngine:

    @staticmethod
    def get_system_prompt(mode: str) -> str:
        """Return the system prompt for the given learning mode."""
        prompts = {
            "Concept-First Learning": CONCEPT_FIRST_SYSTEM,
            "Reverse Engineering":    REVERSE_ENGINEERING_SYSTEM,
            "Visual Learning":        VISUAL_SYSTEM,
        }
        return prompts.get(mode, CONCEPT_FIRST_SYSTEM)

    @staticmethod
    async def generate_response(mode: str, topic: str, code: str = None, pdf_id: str = None, chapter_ref: str = None) -> dict:
        """
        Full multi-agent pipeline:

        Agent 1: Keyword Extractor
          → Converts natural language input to clean topic for RAG

        RAG: Context Retrieval
          → Wikipedia + DuckDuckGo searched on clean topic
          → Context injected into prompt

        Agent 2: Explanation Generator
          → Chain of Thought reasoning
          → Mode-specific structured response
          → Grounded in RAG but thinks independently
        """

        # ── Agent 1: Extract clean topic ─────────────────────────────────────
        # When PDF is active, skip keyword extraction for RAG —
        # the PDF content IS the context. Only extract for web RAG fallback.
        clean_topic = extract_keyword(topic)

        # ── PDF: Inject uploaded document context if provided ─────────────────
        # Do this BEFORE web RAG so we know whether to skip/reduce web search
        pdf_context = ""
        is_pdf      = False
        if pdf_id:
            pdf_context = get_pdf_context(pdf_id, chapter_ref)
            if pdf_context:
                logger.info(f"[PDF] Injecting context from document ({len(pdf_context)} chars)")
                is_pdf = True

        # ── RAG: Only fetch web context if no PDF, or PDF found nothing ──────
        context = ""
        if not is_pdf:
            # No PDF — use full web RAG pipeline
            context = await retrieve_context(clean_topic, mode)
        else:
            # PDF is primary source — skip web RAG, PDF context is enough
            context = pdf_context

        # ── Agent 2: Build prompt and generate explanation ────────────────────
        system_prompt = AIEngine.get_system_prompt(mode)

        if mode == "Concept-First Learning":
            user_prompt = build_concept_first_prompt(
                clean_topic, topic, code, context, is_pdf
            )
        elif mode == "Reverse Engineering":
            user_prompt = build_reverse_engineering_prompt(
                clean_topic, topic, code, context, is_pdf
            )
        else:  # Visual Learning
            user_prompt = build_visual_prompt(clean_topic, topic, context, is_pdf)

        # When PDF mode: instruct to teach from book content
        if is_pdf and chapter_ref:
            user_prompt += (
                f"\n\nTeach from the provided textbook content. "
                f"Cover the key concepts and subtopics found in the text. "
                f"Be specific — use the actual terminology, equations, and examples from the book."
            )

        # ── LLM Call ─────────────────────────────────────────────────────────
        try:
            chat_completion = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1500,
                top_p=0.9,
            )
            raw_text = chat_completion.choices[0].message.content

        except Exception as e:
            import traceback
            print(f"\n[AI ENGINE ERROR] {str(e)}")
            traceback.print_exc()
            return {
                "mode":        mode,
                "explanation": f"AI Engine error: {str(e)}",
                "raw":         f"Error: {str(e)}",
                "steps":       ["Error occurred during generation."],
                "exercise":    "Please try again.",
            }

        # ── Parse and return structured response ──────────────────────────────
        return parse_response(raw_text, mode)

    @staticmethod
    async def generate_chunk_response(
        mode: str,
        topic: str,
        chunk_title: str,
        chunk_index: int,
        total_chunks: int,
        pdf_context: str,
    ) -> dict:
        """
        Teach one specific subtopic from a PDF chapter.
        Token-safe: only sends one section of text at a time.

        Pipeline:
          1. Build focused prompt for this ONE section
          2. Call LLM with strict token budget
          3. Parse and return structured response
        """
        system_prompt = AIEngine.get_system_prompt(mode)
        position_note = f"(Part {chunk_index + 1} of {total_chunks})"

        user_prompt = (
            f"You are teaching from an uploaded textbook. "
            f"The following is the ACTUAL textbook content for this section:\n\n"
            f"{pdf_context}\n\n"
            f"---\n\n"
            f"Topic: {topic}\n"
            f"Section: {chunk_title} {position_note}\n\n"
            f"Using the textbook content above, teach this section with DEPTH and DETAIL:\n"
            f"- Extract and explain every key concept mentioned in the text\n"
            f"- Include any equations or formulas from the text (explain each variable)\n"
            f"- Use the specific examples and experiments from the textbook\n"
            f"- Reference specific equation numbers if mentioned (e.g. Equation 1-37)\n"
            f"- Do NOT summarize — explain each concept fully\n\n"
            f"Follow the learning structure exactly."
        )

        try:
            chat_completion = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.5,    # lower = more focused on textbook content
                max_tokens=2000,    # more room for detailed explanations
                top_p=0.9,
            )
            raw_text = chat_completion.choices[0].message.content
            logger.info(f"[Chunk] Generated chunk {chunk_index+1}/{total_chunks}: {chunk_title}")

        except Exception as e:
            import traceback
            print(f"\n[CHUNK ERROR] {str(e)}")
            traceback.print_exc()
            return {
                "mode":        mode,
                "explanation": f"Error: {str(e)}",
                "raw":         f"Error: {str(e)}",
                "steps":       ["Error occurred."],
                "exercise":    "Please try again.",
                "real_world":  "",
            }

        result = parse_response(raw_text, mode)
        return result

