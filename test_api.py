"""
test_api.py — LearnPilot API Test Suite v2
Tests all three modes + natural language input handling.
Usage: python3 test_api.py
"""

import requests

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    print("\n── Health Check ──────────────────────────────")
    r = requests.get(f"{BASE_URL}/health")
    print(f"Status: {r.status_code} | Response: {r.json()}")

def test_concept_first():
    print("\n── Test: Concept-First Learning ──────────────")
    payload = {"topic": "Binary Search", "mode": "Concept-First Learning", "code_snippet": None}
    r = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Mode: {data['mode']}")
        print(f"Steps: {data['steps']}")
        print(f"Exercise: {data['exercise'][:100]}...")
        print(f"Raw preview: {data['raw'][:200]}...")

def test_natural_language():
    print("\n── Test: Natural Language Input ──────────────")
    payload = {"topic": "why do we need pointers in C programming?", "mode": "Concept-First Learning", "code_snippet": None}
    r = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Mode: {data['mode']}")
        print(f"Steps: {data['steps']}")
        print(f"Exercise: {data['exercise'][:100]}...")
        print(f"Raw preview: {data['raw'][:200]}...")

def test_reverse_engineering():
    print("\n── Test: Reverse Engineering ─────────────────")
    payload = {"topic": "Merge Sort", "mode": "Reverse Engineering", "code_snippet": None}
    r = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Mode: {data['mode']}")
        print(f"Steps: {data['steps']}")
        print(f"Exercise: {data['exercise'][:100]}...")

def test_visual_cs():
    print("\n── Test: Visual Learning (CS topic) ──────────")
    payload = {"topic": "Binary Search Tree", "mode": "Visual Learning", "code_snippet": None}
    r = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Mode: {data['mode']}")
        print(f"Steps: {data['steps']}")
        has_mermaid = "```mermaid" in data['raw']
        print(f"Mermaid diagram generated: {has_mermaid}")
        print(f"Raw preview: {data['raw'][:300]}...")

def test_visual_non_cs():
    print("\n── Test: Visual Learning (non-CS topic) ──────")
    payload = {"topic": "how does photosynthesis work", "mode": "Visual Learning", "code_snippet": None}
    r = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Mode: {data['mode']}")
        has_mermaid = "```mermaid" in data['raw']
        has_search  = "Search Further" in data['raw']
        print(f"Mermaid diagram: {has_mermaid} | Search suggestions: {has_search}")
        print(f"Raw preview: {data['raw'][:300]}...")

def test_history():
    print("\n── Test: History Endpoint ────────────────────")
    r = requests.get(f"{BASE_URL}/history")
    print(f"Status: {r.status_code} | Sessions stored: {len(r.json())}")

if __name__ == "__main__":
    print("LearnPilot API Test Suite v2")
    print("Ensure server is running: uvicorn main:app --reload")
    try:
        test_health()
        test_concept_first()
        test_natural_language()
        test_reverse_engineering()
        test_visual_cs()
        test_visual_non_cs()
        test_history()
        print("\n✓ All tests completed.")
    except requests.exceptions.ConnectionError:
        print("\n✗ Connection failed. Start server: uvicorn main:app --reload")
