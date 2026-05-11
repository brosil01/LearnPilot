"""
main.py — LearnPilot FastAPI Backend v3
New endpoints:
  POST /plan           — returns learning plan (subtopics list) for a chapter
  POST /generate-chunk — teaches one specific subtopic (page range)
"""

import time
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from ai_engine import AIEngine
from logger_util import SystemMonitor
from history_service import HistoryService
from pdf_service import (
    save_pdf, get_uploaded_files, delete_pdf,
    get_learning_plan, get_chunk_context
)

app = FastAPI(title="LearnPilot API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────

class LearningRequest(BaseModel):
    topic:        str
    mode:         str
    code_snippet: Optional[str] = None
    pdf_id:       Optional[str] = None
    chapter_ref:  Optional[str] = None

class ChunkRequest(BaseModel):
    topic:       str           # full original question e.g. "teach me chapter 1"
    mode:        str
    pdf_id:      str
    page_start:  int
    page_end:    int
    chunk_title: str           # e.g. "1-3 The Lorentz Transformation"
    chunk_index: int           # 0-based position in plan
    total_chunks: int          # total number of chunks

class PlanRequest(BaseModel):
    pdf_id:      str
    chapter_ref: str           # e.g. "chapter 1"

class LearningResponse(BaseModel):
    mode:        str
    explanation: str
    raw:         str
    steps:       List[str]
    exercise:    str
    real_world:  str = ""

class SubTopic(BaseModel):
    title:      str
    page_start: int
    page_end:   int
    section:    str

class PlanResponse(BaseModel):
    chapter_ref: str
    subtopics:   List[SubTopic]

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "LearnPilot API running", "version": "3.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/history")
async def get_history():
    return HistoryService.get_history()

@app.post("/generate", response_model=LearningResponse)
async def generate(request: LearningRequest):
    start_time = time.time()
    SystemMonitor.log_request(request.mode, request.topic)
    result = await AIEngine.generate_response(
        request.mode, request.topic, request.code_snippet,
        request.pdf_id, request.chapter_ref,
    )
    HistoryService.save_session(request.mode, request.topic, result)
    SystemMonitor.log_performance(start_time)
    return result

@app.post("/plan", response_model=PlanResponse)
async def get_plan(request: PlanRequest):
    """
    Build a learning plan for a chapter.
    Returns ordered list of subtopics with page ranges.
    Frontend uses this to drive the Next button navigation.
    """
    subtopics = get_learning_plan(request.pdf_id, request.chapter_ref)
    if not subtopics:
        raise HTTPException(404, f"Could not build plan for '{request.chapter_ref}'")
    return PlanResponse(chapter_ref=request.chapter_ref, subtopics=subtopics)

@app.post("/generate-chunk", response_model=LearningResponse)
async def generate_chunk(request: ChunkRequest):
    """
    Teach one specific subtopic (page range) from the PDF.
    Called for each chunk as user clicks Next.
    """
    start_time = time.time()

    # Get text for this specific page range
    pdf_context = get_chunk_context(request.pdf_id, request.page_start, request.page_end)
    if not pdf_context:
        raise HTTPException(404, "Could not extract content for this section")

    SystemMonitor.log_request(request.mode, request.chunk_title)

    result = await AIEngine.generate_chunk_response(
        mode        = request.mode,
        topic       = request.topic,
        chunk_title = request.chunk_title,
        chunk_index = request.chunk_index,
        total_chunks= request.total_chunks,
        pdf_context = pdf_context,
    )

    SystemMonitor.log_performance(start_time)
    return result

# ── PDF Upload Routes ─────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 50MB.")
    try:
        meta = await save_pdf(file_bytes, file.filename)
        return {"success": True, "file_id": meta["id"],
                "name": meta["name"], "pages": meta["pages"]}
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")

@app.get("/files")
async def list_files():
    return get_uploaded_files()

@app.delete("/files/{file_id}")
async def remove_file(file_id: str):
    if not delete_pdf(file_id):
        raise HTTPException(404, "File not found.")
    return {"success": True}


# ── Feature Endpoints ─────────────────────────────────────────────────────────
from features import generate_more_context, generate_quiz, generate_exercises, fetch_related_links

class MoreContextRequest(BaseModel):
    topic:           str
    mode:            str
    already_covered: List[str] = []   # raw responses already shown
    rag_context:     str = ""

class QuizRequest(BaseModel):
    topic:        str
    all_contexts: List[str]           # all raw responses accumulated
    num_questions: int = 5

class ExerciseRequest(BaseModel):
    topic:         str
    all_contexts:  List[str]
    num_questions: int = 4

class LinksRequest(BaseModel):
    topic: str

@app.post("/more-context")
async def more_context(request: MoreContextRequest):
    result = await generate_more_context(
        request.topic,
        request.mode,
        request.already_covered,
        request.rag_context,
    )
    return result

@app.post("/quiz")
async def quiz(request: QuizRequest):
    questions = await generate_quiz(
        request.topic,
        request.all_contexts,
        request.num_questions,
    )
    return {"topic": request.topic, "questions": questions}

@app.post("/exercises")
async def exercises(request: ExerciseRequest):
    questions = await generate_exercises(
        request.topic,
        request.all_contexts,
        request.num_questions,
    )
    return {"topic": request.topic, "exercises": questions}

@app.post("/related-links")
async def related_links(request: LinksRequest):
    links = await fetch_related_links(request.topic)
    return {"topic": request.topic, "links": links}
