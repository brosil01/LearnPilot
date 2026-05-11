"""
features.py — LearnPilot Extended Features Engine

Handles:
  - More Context   → generates additional content covering DIFFERENT aspects
  - Quiz           → MCQ questions based on ALL accumulated context
  - Exercises      → Open-ended questions based on ALL accumulated context
  - Related Links  → RAG fetches real helpful URLs for the topic
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("LearnPilot")

MODEL_ID     = os.getenv("MODEL_ID", "llama-3.1-8b-instant")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client       = Groq(api_key=GROQ_API_KEY)


def _call_llm(system: str, user: str, max_tokens: int = 1500, temp: float = 0.7) -> str:
    """Shared LLM call helper."""
    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temp,
            max_tokens=max_tokens,
            top_p=0.9,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[Features] LLM call failed: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# MORE CONTEXT
# Generates DIFFERENT aspects not already covered
# ══════════════════════════════════════════════════════════════════════════════

async def generate_more_context(
    topic: str,
    mode: str,
    already_covered: list[str],   # list of raw responses already shown
    rag_context: str = "",
) -> dict:
    """
    Generate additional content covering DIFFERENT aspects of the topic.
    Receives what was already covered so it avoids repetition.
    """

    # Summarize what was already covered (keep short for token budget)
    covered_summary = ""
    if already_covered:
        # Extract key section headings from previous responses
        all_headings = []
        for resp in already_covered:
            headings = re.findall(r"## (.+)", resp)
            all_headings.extend(headings)
        covered_summary = (
            f"The learner has already seen content covering: "
            f"{', '.join(set(all_headings))}. "
            f"Do NOT repeat these aspects."
        )

    system = f"""You are LearnPilot, an expert educational AI assistant.
You are providing ADDITIONAL context on a topic the learner is already studying.
Your job: cover aspects, angles, or depth NOT already covered.

{covered_summary}

Generate your response using these sections:

## Additional Concept
A different angle, deeper aspect, or related concept not covered before.

## Deeper Explanation
Go further into the mechanics, theory, or nuance of this new angle.

## Additional Example
A NEW concrete example — different from any previously shown.
Match to subject: science=real phenomena, history=real events, math=worked numbers, code=working code.

## Key Insight
One important insight or takeaway that adds real value beyond what was already taught.

## Real World Applications
2-3 NEW real-world applications not mentioned before. Specific names and how it applies.

CRITICAL: Write content directly — no preamble. Cover genuinely different material.
"""

    rag_block = f"Additional context:\n{rag_context}\n\n---\n\n" if rag_context else ""
    user = f"{rag_block}Topic: {topic}\nProvide additional context covering different aspects."

    raw = _call_llm(system, user, max_tokens=1500)

    # Parse sections
    sections = {
        m.group(1).strip(): m.group(2).strip()
        for m in re.finditer(r"##\s+(.+?)\n(.*?)(?=\n##\s|\Z)", raw, re.DOTALL)
    }

    return {
        "raw":         raw,
        "type":        "more_context",
        "title":       sections.get("Additional Concept", "Additional Context")[:80],
        "insight":     sections.get("Key Insight", ""),
        "real_world":  sections.get("Real World Applications", ""),
    }


# ══════════════════════════════════════════════════════════════════════════════
# QUIZ — MCQ based on ALL accumulated contexts
# ══════════════════════════════════════════════════════════════════════════════

async def generate_quiz(
    topic: str,
    all_contexts: list[str],   # all raw responses accumulated
    num_questions: int = 5,
) -> list[dict]:
    """
    Generate multiple-choice quiz questions based on ALL accumulated context.
    More context clicks = more material to draw questions from.
    """

    # Combine contexts — take first 4000 chars total for token safety
    combined = "\n\n---\n\n".join(all_contexts)[:4000]

    system = """You are a quiz generator for LearnPilot.
Generate multiple-choice questions based STRICTLY on the provided content.
Every question and every correct answer MUST be derivable from the content given.

Return ONLY valid JSON — no markdown, no explanation, no preamble.
Format exactly:
[
  {
    "question": "Question text here?",
    "options": ["A) Option one", "B) Option two", "C) Option three", "D) Option four"],
    "correct": "A",
    "explanation": "Brief explanation of why A is correct."
  }
]
"""

    user = (
        f"Content to base questions on:\n{combined}\n\n"
        f"Generate exactly {num_questions} multiple-choice questions. "
        f"Mix difficulty — some straightforward, some requiring deeper understanding. "
        f"Return ONLY the JSON array."
    )

    raw = _call_llm(system, user, max_tokens=2000, temp=0.4)

    # Parse JSON safely
    try:
        # Strip markdown fences if present
        clean = re.sub(r"```json\s*|```\s*", "", raw).strip()
        # Find JSON array
        match = re.search(r"\[.*\]", clean, re.DOTALL)
        if match:
            questions = json.loads(match.group())
            logger.info(f"[Quiz] Generated {len(questions)} questions for '{topic}'")
            return questions
    except Exception as e:
        logger.error(f"[Quiz] JSON parse failed: {e}")

    return []


# ══════════════════════════════════════════════════════════════════════════════
# EXERCISES — Open-ended questions based on ALL accumulated contexts
# ══════════════════════════════════════════════════════════════════════════════

async def generate_exercises(
    topic: str,
    all_contexts: list[str],
    num_questions: int = 4,
) -> list[dict]:
    """
    Generate open-ended exercise questions based on ALL accumulated context.
    Not multiple choice — requires the learner to construct an answer.
    """

    combined = "\n\n---\n\n".join(all_contexts)[:4000]

    system = """You are an exercise generator for LearnPilot.
Generate open-ended exercise questions based STRICTLY on the provided content.
Questions should require the learner to think, apply, analyze, or construct — not just recall.

Return ONLY valid JSON — no markdown, no explanation.
Format exactly:
[
  {
    "question": "Open-ended question here?",
    "type": "apply|analyze|explain|calculate|compare",
    "hint": "A brief hint if needed, or empty string.",
    "sample_answer": "A model answer the learner can check against."
  }
]
"""

    user = (
        f"Content:\n{combined}\n\n"
        f"Generate exactly {num_questions} open-ended exercise questions. "
        f"Mix types: some application, some analysis, some explanation. "
        f"For math/physics: include calculation questions with numbers from the content. "
        f"Return ONLY the JSON array."
    )

    raw = _call_llm(system, user, max_tokens=2000, temp=0.5)

    try:
        clean = re.sub(r"```json\s*|```\s*", "", raw).strip()
        match = re.search(r"\[.*\]", clean, re.DOTALL)
        if match:
            exercises = json.loads(match.group())
            logger.info(f"[Exercises] Generated {len(exercises)} exercises for '{topic}'")
            return exercises
    except Exception as e:
        logger.error(f"[Exercises] JSON parse failed: {e}")

    return []


# ══════════════════════════════════════════════════════════════════════════════
# RELATED LINKS — RAG fetches real helpful URLs
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_related_links(topic: str) -> list[dict]:
    """
    Fetch real, helpful related links for the topic using:
    - DuckDuckGo Instant Answer API (gets Wikipedia + related)
    - Wikipedia API for direct article URL
    - Curated source list for known domains (Khan Academy, MIT OCW, etc.)

    Returns list of {title, url, description, source_type}
    """
    links = []

    # 1. Wikipedia link
    try:
        encoded = urllib.parse.quote(topic)
        url     = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req     = urllib.request.Request(url, headers={"User-Agent": "LearnPilot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            if data.get("extract") and data.get("content_urls"):
                links.append({
                    "title":       data.get("title", topic),
                    "url":         data["content_urls"]["desktop"]["page"],
                    "description": data.get("extract", "")[:200] + "...",
                    "source":      "Wikipedia",
                    "icon":        "📖",
                })
    except Exception as e:
        logger.warning(f"[Links] Wikipedia failed: {e}")

    # 2. DuckDuckGo related topics
    try:
        encoded = urllib.parse.quote(f"{topic} tutorial explanation")
        url     = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req     = urllib.request.Request(url, headers={"User-Agent": "LearnPilot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())

            # AbstractURL — usually Wikipedia or official source
            if data.get("AbstractURL") and data.get("AbstractText"):
                if not any(l["url"] == data["AbstractURL"] for l in links):
                    links.append({
                        "title":       data.get("Heading", topic),
                        "url":         data["AbstractURL"],
                        "description": data["AbstractText"][:200] + "...",
                        "source":      data.get("AbstractSource", "Reference"),
                        "icon":        "🔗",
                    })

            # Related topics from DDG
            for item in data.get("RelatedTopics", [])[:4]:
                if isinstance(item, dict) and item.get("FirstURL") and item.get("Text"):
                    links.append({
                        "title":       item["Text"][:60],
                        "url":         item["FirstURL"],
                        "description": item["Text"][:150],
                        "source":      "DuckDuckGo",
                        "icon":        "🔍",
                    })
    except Exception as e:
        logger.warning(f"[Links] DDG links failed: {e}")

    # 3. Add curated educational sources based on topic classification
    topic_lower = topic.lower()

    cs_keywords    = {"algorithm", "programming", "code", "python", "java", "data structure",
                      "binary", "sort", "tree", "graph", "recursion", "machine learning"}
    math_keywords  = {"calculus", "algebra", "math", "equation", "theorem", "statistics",
                      "probability", "matrix", "vector", "physics", "quantum"}
    bio_keywords   = {"biology", "cell", "dna", "gene", "chemistry", "photosynthesis",
                      "anatomy", "evolution", "ecology", "medicine"}

    if any(k in topic_lower for k in cs_keywords):
        links.append({
            "title":       f"GeeksForGeeks: {topic}",
            "url":         f"https://www.geeksforgeeks.org/?s={urllib.parse.quote(topic)}",
            "description": "Detailed tutorials, examples and practice problems for CS topics.",
            "source":      "GeeksForGeeks",
            "icon":        "💻",
        })
        links.append({
            "title":       f"Khan Academy: {topic}",
            "url":         f"https://www.khanacademy.org/search?referer=%2F&page_search_query={urllib.parse.quote(topic)}",
            "description": "Free video lessons and practice exercises.",
            "source":      "Khan Academy",
            "icon":        "🎓",
        })

    elif any(k in topic_lower for k in math_keywords):
        links.append({
            "title":       f"Khan Academy: {topic}",
            "url":         f"https://www.khanacademy.org/search?referer=%2F&page_search_query={urllib.parse.quote(topic)}",
            "description": "Free video lessons, worked examples, and practice.",
            "source":      "Khan Academy",
            "icon":        "🎓",
        })
        links.append({
            "title":       f"MIT OpenCourseWare: {topic}",
            "url":         f"https://ocw.mit.edu/search/?q={urllib.parse.quote(topic)}",
            "description": "Free MIT course materials, lecture notes, and problem sets.",
            "source":      "MIT OCW",
            "icon":        "🏛️",
        })

    elif any(k in topic_lower for k in bio_keywords):
        links.append({
            "title":       f"Khan Academy: {topic}",
            "url":         f"https://www.khanacademy.org/search?referer=%2F&page_search_query={urllib.parse.quote(topic)}",
            "description": "Free video lessons and practice exercises.",
            "source":      "Khan Academy",
            "icon":        "🎓",
        })
        links.append({
            "title":       f"NIH: {topic}",
            "url":         f"https://www.ncbi.nlm.nih.gov/search/research-articles/?term={urllib.parse.quote(topic)}",
            "description": "Peer-reviewed research articles from the National Institutes of Health.",
            "source":      "NIH / PubMed",
            "icon":        "🔬",
        })

    else:
        # General fallback
        links.append({
            "title":       f"Khan Academy: {topic}",
            "url":         f"https://www.khanacademy.org/search?referer=%2F&page_search_query={urllib.parse.quote(topic)}",
            "description": "Free video lessons and practice exercises.",
            "source":      "Khan Academy",
            "icon":        "🎓",
        })
        links.append({
            "title":       f"YouTube: {topic} explained",
            "url":         f"https://www.youtube.com/results?search_query={urllib.parse.quote(topic + ' explained')}",
            "description": "Video explanations and tutorials on YouTube.",
            "source":      "YouTube",
            "icon":        "▶️",
        })

    # Deduplicate by URL and return max 6
    seen_urls = set()
    unique    = []
    for link in links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            unique.append(link)

    logger.info(f"[Links] Found {len(unique)} links for '{topic}'")
    return unique[:6]
