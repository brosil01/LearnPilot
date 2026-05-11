"""
rag_service.py — LearnPilot RAG Service v3
Smart source routing — picks sources based on subject area:
  CS / Programming  → Wikipedia + Stack Exchange + arXiv
  Math / Physics    → Wikipedia + arXiv
  Biology / Health  → Wikipedia + PubMed
  General / Other   → Wikipedia + DuckDuckGo Instant
All free, zero API keys, pure stdlib.
"""

import re
import asyncio
import logging
import urllib.request
import urllib.parse
import json
import gzip

logger = logging.getLogger("LearnPilot")

# ── Subject Keywords ──────────────────────────────────────────────────────────

CS_KEYWORDS = {
    "algorithm","data structure","programming","python","java","javascript",
    "c++","c programming","code","coding","software","binary","tree","graph",
    "array","linked list","stack","queue","hash","sorting","search","recursion",
    "dynamic programming","big o","complexity","database","sql","api","web",
    "frontend","backend","machine learning","neural network","ai","deep learning",
    "compiler","operating system","network","tcp","http","rest","object oriented",
    "inheritance","polymorphism","class","function","variable","loop","pointer",
    "memory","heap","bit","byte","boolean","integer","string","merge sort",
    "quick sort","bubble sort","binary search","bfs","dfs","react","node",
    "html","css","git","linux","docker","kubernetes","encryption","cybersecurity",
    "blockchain","concurrency","thread","process","pointer",
    "sort","sorting algorithm","merge sort","quick sort","bubble sort",
}

MATH_PHYSICS_KEYWORDS = {
    "math","mathematics","calculus","algebra","geometry","trigonometry",
    "statistics","probability","linear algebra","matrix","vector","integral",
    "derivative","differential","equation","theorem","proof","number theory",
    "topology","physics","mechanics","quantum","relativity","thermodynamics",
    "electromagnetism","optics","wave","particle","force","energy","momentum",
    "gravity","newton","einstein","fourier","laplace","euler","prime number",
    "graph theory","set theory","combinatorics","permutation","combination",
    "logarithm","exponential","polynomial","limit","series","fluid dynamics",
    "nuclear","atomic","molecule","entropy","frequency",
}

BIO_HEALTH_KEYWORDS = {
    "biology","chemistry","medicine","health","anatomy","cell","dna","rna",
    "protein","enzyme","gene","genetics","evolution","photosynthesis","respiration",
    "ecosystem","organism","bacteria","virus","immune","blood","heart","brain",
    "neuron","muscle","bone","disease","cancer","diabetes","covid","vaccine",
    "drug","pharmacology","nutrition","metabolism","hormone","nervous system",
    "digestive","respiratory","cardiovascular","reproduction","embryo","mutation",
    "biodiversity","ecology","food chain","symbiosis","taxonomy","species",
}


def classify_subject(topic: str) -> str:
    """
    Classify topic into subject area using word-aware matching.
    Handles plurals and word boundaries correctly:
      - "pointers" matches keyword "pointer" (word starts with keyword)
      - "revolution" does NOT match keyword "evolution" (not a word start)
    """
    words = topic.lower().split()

    def score(keywords):
        count = 0
        for kw in keywords:
            kw_words = kw.split()
            # Single-word keyword: check if any topic word starts with it
            if len(kw_words) == 1:
                if any(w.startswith(kw) for w in words):
                    count += 1
            else:
                # Multi-word keyword: check if the phrase appears in topic
                if kw in topic.lower():
                    # Verify it's not a substring of a longer word
                    idx = topic.lower().find(kw)
                    before = topic.lower()[idx-1] if idx > 0 else " "
                    after  = topic.lower()[idx+len(kw)] if idx+len(kw) < len(topic) else " "
                    if before in (" ", "-") and after in (" ", "-", "s", "ed", "ing", ""):
                        count += 1
        return count

    cs   = score(CS_KEYWORDS)
    math = score(MATH_PHYSICS_KEYWORDS)
    bio  = score(BIO_HEALTH_KEYWORDS)
    best = max(cs, math, bio)
    if best == 0:    return "general"
    if cs == best:   return "cs"
    if math == best: return "math_physics"
    return "bio_health"


# ── Sources ───────────────────────────────────────────────────────────────────

def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "LearnPilot/1.0 (educational project)"}
    )
    with urllib.request.urlopen(req, timeout=6) as r:
        return r.read()


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def search_wikipedia(topic: str) -> str:
    try:
        def _f():
            raw = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic)}")
            return json.loads(raw.decode()).get("extract", "")
        return await _run(_f)
    except Exception as e:
        logger.warning(f"[RAG] Wikipedia failed '{topic}': {e}"); return ""


async def search_stack_exchange(topic: str) -> str:
    try:
        def _f():
            url = (f"https://api.stackexchange.com/2.3/search/advanced"
                   f"?order=desc&sort=votes&q={urllib.parse.quote(topic)}"
                   f"&site=stackoverflow&pagesize=3&filter=default")
            raw  = _get(url)
            try:    data = json.loads(gzip.decompress(raw).decode())
            except: data = json.loads(raw.decode())
            items = data.get("items", [])
            out = []
            for item in items[:3]:
                title = item.get("title","")
                if title:
                    out.append(f"Q: {title}")
            return "\n".join(out)
        return await _run(_f)
    except Exception as e:
        logger.warning(f"[RAG] StackExchange failed '{topic}': {e}"); return ""


async def search_arxiv(topic: str) -> str:
    try:
        def _f():
            url = (f"https://export.arxiv.org/api/query"
                   f"?search_query=all:{urllib.parse.quote(topic)}"
                   f"&start=0&max_results=2&sortBy=relevance&sortOrder=descending")
            content = _get(url).decode()
            titles    = re.findall(r"<title>(.*?)</title>",   content, re.DOTALL)
            summaries = re.findall(r"<summary>(.*?)</summary>",content, re.DOTALL)
            titles    = [t.strip() for t in titles[1:3]]
            summaries = [re.sub(r"\s+"," ",s).strip()[:350] for s in summaries[:2]]
            return "\n\n".join(
                f"Paper: {t}\n{s}" for t,s in zip(titles,summaries)
            )
        return await _run(_f)
    except Exception as e:
        logger.warning(f"[RAG] arXiv failed '{topic}': {e}"); return ""


async def search_pubmed(topic: str) -> str:
    try:
        def _f():
            enc = urllib.parse.quote(topic)
            raw = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                       f"?db=pubmed&term={enc}&retmax=2&retmode=json")
            ids = json.loads(raw.decode()).get("esearchresult",{}).get("idlist",[])
            if not ids: return ""
            raw2 = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                        f"?db=pubmed&id={','.join(ids[:2])}&retmode=json")
            result_map = json.loads(raw2.decode()).get("result",{})
            out = []
            for uid in ids[:2]:
                a = result_map.get(uid,{})
                t = a.get("title",""); s = a.get("source",""); d = a.get("pubdate","")
                if t: out.append(f"Study: {t} ({s}, {d})")
            return "\n".join(out)
        return await _run(_f)
    except Exception as e:
        logger.warning(f"[RAG] PubMed failed '{topic}': {e}"); return ""


async def search_ddg_instant(query: str) -> str:
    try:
        def _f():
            enc = urllib.parse.quote(query)
            raw = _get(f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1&skip_disambig=1")
            data     = json.loads(raw.decode())
            abstract = data.get("AbstractText","")
            related  = [t.get("Text","") for t in data.get("RelatedTopics",[])[:3]
                        if isinstance(t,dict) and t.get("Text")]
            return " ".join(p for p in [abstract]+related if p)
        return await _run(_f)
    except Exception as e:
        logger.warning(f"[RAG] DDG failed '{query}': {e}"); return ""


# ── Text Cleaner ──────────────────────────────────────────────────────────────

def clean_text(text: str, max_chars: int = 700) -> str:
    if not text: return ""
    text = re.sub(r"\s+"," ",text).strip()
    return text[:max_chars]+"..." if len(text) > max_chars else text


# ── Smart Router ──────────────────────────────────────────────────────────────

async def route_and_fetch(topic: str, subject: str) -> list:
    if subject == "cs":
        logger.info("[RAG] Route: CS → Wikipedia + Stack Exchange + arXiv")
        results = await asyncio.gather(
            search_wikipedia(topic),
            search_stack_exchange(topic),
            search_arxiv(topic),
            return_exceptions=True,
        )
        labels = ["Wikipedia","Stack Overflow","arXiv"]

    elif subject == "math_physics":
        logger.info("[RAG] Route: Math/Physics → Wikipedia + arXiv")
        results = await asyncio.gather(
            search_wikipedia(topic),
            search_arxiv(topic),
            return_exceptions=True,
        )
        labels = ["Wikipedia","arXiv"]

    elif subject == "bio_health":
        logger.info("[RAG] Route: Biology/Health → Wikipedia + PubMed")
        results = await asyncio.gather(
            search_wikipedia(topic),
            search_pubmed(topic),
            return_exceptions=True,
        )
        labels = ["Wikipedia","PubMed"]

    else:
        logger.info("[RAG] Route: General → Wikipedia + DuckDuckGo")
        results = await asyncio.gather(
            search_wikipedia(topic),
            search_ddg_instant(f"{topic} explained overview"),
            return_exceptions=True,
        )
        labels = ["Wikipedia","Web"]

    return list(zip(labels, results))


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def retrieve_context(topic: str, mode: str) -> str:
    subject      = classify_subject(topic)
    logger.info(f"[RAG] '{topic}' → subject: {subject}")

    label_results = await route_and_fetch(topic, subject)

    context_parts = []
    seen          = set()

    for label, raw in label_results:
        if isinstance(raw, Exception) or not raw:
            continue
        text = clean_text(raw)
        if not text or text[:80] in seen:
            continue
        seen.add(text[:80])
        context_parts.append(f"[{label}: {topic}]\n{text}")

    if not context_parts:
        logger.info("[RAG] No context retrieved — LLM will use its own knowledge")
        return ""

    context = "\n\n".join(context_parts)
    logger.info(f"[RAG] Retrieved {len(context_parts)} source(s) ({len(context)} chars) [{subject}]")
    return context
