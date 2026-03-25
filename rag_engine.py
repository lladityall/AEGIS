#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║           AEGIS  —  rag_engine.py                        ║
║   Document ingestion + retrieval-augmented generation.   ║
║                                                          ║
║   Supports: .txt  .md  .pdf  .docx  .csv  .json         ║
║   Embedding: Ollama  nomic-embed-text  (reuses your      ║
║              existing Ollama install — NO PyTorch)       ║
║   Vector store: in-memory cosine similarity (stdlib)     ║
║   Persistence: ~/.aegis/rag_store/  (JSON only)          ║
╚══════════════════════════════════════════════════════════╝

DEPENDENCIES — total ~15 MB (no PyTorch, no sentence-transformers):
    pip install ollama PyPDF2 python-docx

Ollama embedding model (pull once, ~274 MB):
    ollama pull nomic-embed-text
"""

import os, json, re, hashlib, math
from pathlib import Path
from typing  import List, Tuple, Optional

# ── Config ────────────────────────────────────────────────
STORE_DIR     = Path.home() / ".aegis" / "rag_store"
CHUNK_SIZE    = 400       # words per chunk
CHUNK_OVERLAP = 60        # overlap between chunks
TOP_K         = 5         # chunks returned per query
MIN_SCORE     = 0.25      # cosine threshold
EMBED_MODEL   = "nomic-embed-text"   # pulled via: ollama pull nomic-embed-text
OLLAMA_HOST   = "https://ollama.com"
OLLAMA_API_KEY= "e367096933634fe4a2c7c722e00a1330.eordImDQUFo0YlUAo-jD-AE0"


# ── Optional imports ──────────────────────────────────────
def _try_import(pkg: str):
    try:
        import importlib
        return importlib.import_module(pkg)
    except ImportError:
        return None


# ── Pure-Python cosine similarity (no numpy needed) ───────
def _cosine(a: list, b: list) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class RAGEngine:
    """
    Lightweight RAG using Ollama's embedding endpoint.
    No PyTorch. No sentence-transformers. Just ollama + stdlib.
    """

    def __init__(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        self._docs:   dict = {}   # doc_id -> {path, name, n_chunks}
        self._chunks: list = []   # [{text, doc_id, doc_name, idx, embedding}]
        self._client       = None
        self._embed_ready  = False
        self._load_store()
        self._init_client()

    # ── Ollama client ─────────────────────────────────────
    def _init_client(self):
        ol = _try_import("ollama")
        if ol is None:
            print("  [RAG] ollama package not found — pip install ollama")
            return
        try:
            from ollama import Client
            self._client = Client(
                host=OLLAMA_HOST,
                headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
            )
            self._embed_ready = True
        except Exception as exc:
            print(f"  [RAG] Ollama client init failed: {exc}")

    # ── Embed via Ollama ──────────────────────────────────
    def _embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Return list of embedding vectors, or None on failure."""
        if not self._embed_ready or self._client is None:
            return None
        try:
            results = []
            for text in texts:
                resp = self._client.embeddings(model=EMBED_MODEL, prompt=text)
                results.append(resp["embedding"])
            return results
        except Exception as exc:
            if "not found" in str(exc).lower() or "pull" in str(exc).lower():
                print(f"\n  [RAG] Embedding model not pulled yet.")
                print(f"  Run once:  ollama pull {EMBED_MODEL}  (~274 MB)\n")
            else:
                print(f"  [RAG] Embedding error: {exc}")
            return None

    # ── Persistence ───────────────────────────────────────
    def _store_path(self) -> Path:
        return STORE_DIR / "store.json"

    def _save_store(self):
        data = {"docs": self._docs, "chunks": self._chunks}
        self._store_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def _load_store(self):
        if self._store_path().exists():
            try:
                data         = json.loads(self._store_path().read_text())
                self._docs   = data.get("docs",   {})
                self._chunks = data.get("chunks", [])
            except Exception:
                pass

    # ── Text extraction ───────────────────────────────────
    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()

        if suffix in {".txt", ".md", ".csv", ".json", ".log", ".rst"}:
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return f"[read error: {e}]"

        if suffix == ".pdf":
            pypdf = _try_import("PyPDF2")
            if pypdf:
                try:
                    reader = pypdf.PdfReader(str(path))
                    return "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                except Exception as e:
                    return f"[pdf error: {e}]"
            try:
                return path.read_bytes().decode("latin-1", errors="replace")
            except Exception as e:
                return f"[pdf fallback error: {e}]"

        if suffix == ".docx":
            docx = _try_import("docx")
            if docx:
                try:
                    doc = docx.Document(str(path))
                    return "\n".join(p.text for p in doc.paragraphs)
                except Exception as e:
                    return f"[docx error: {e}]"

        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[unsupported: {e}]"

    # ── Chunking ──────────────────────────────────────────
    def _chunk(self, text: str) -> List[str]:
        words = text.split()
        chunks, i = [], 0
        while i < len(words):
            chunk = " ".join(words[i: i + CHUNK_SIZE])
            chunks.append(chunk)
            i += CHUNK_SIZE - CHUNK_OVERLAP
        return [c for c in chunks if len(c.strip()) > 30]

    # ── Ingest ────────────────────────────────────────────
    def ingest(self, path_str: str) -> str:
        path   = Path(path_str).expanduser().resolve()
        if not path.exists():
            return f"File not found: {path}"

        doc_id = hashlib.md5(str(path).encode()).hexdigest()[:12]
        if doc_id in self._docs:
            return f"Already loaded: {path.name}"

        text   = self._extract_text(path)
        chunks = self._chunk(text)
        if not chunks:
            return f"No usable text found in: {path.name}"

        print(f"  Embedding {len(chunks)} chunks via Ollama ({EMBED_MODEL})...")
        embeddings = self._embed(chunks)

        self._docs[doc_id] = {
            "path": str(path), "name": path.name, "n_chunks": len(chunks)
        }
        for idx, chunk in enumerate(chunks):
            self._chunks.append({
                "text":      chunk,
                "doc_id":    doc_id,
                "doc_name":  path.name,
                "idx":       idx,
                "embedding": embeddings[idx] if embeddings else None,
            })

        self._save_store()
        mode = "embedded" if embeddings else "keyword-only (run: ollama pull nomic-embed-text)"
        return f"Ingested '{path.name}' — {len(chunks)} chunks, {mode}"

    # ── Query ─────────────────────────────────────────────
    def query(self, question: str, top_k: int = TOP_K) -> str:
        if not self._chunks:
            return ""

        # Semantic search
        q_embs = self._embed([question])
        if q_embs is not None:
            q_vec  = q_embs[0]
            scored = []
            for chunk in self._chunks:
                if chunk.get("embedding") is None:
                    continue
                score = _cosine(q_vec, chunk["embedding"])
                scored.append((chunk["doc_name"], chunk["text"], score))
            scored.sort(key=lambda x: x[2], reverse=True)
            top = [(d, t, s) for d, t, s in scored[:top_k] if s >= MIN_SCORE]
            if top:
                return self._format_context(top)

        # Keyword fallback
        stop = {
            "the","a","an","is","are","was","were","what","how","why","when",
            "where","who","which","do","does","did","can","could","should",
            "would","will","i","me","my","to","of","in","on","at","for",
            "with","and","or","not","it","this","that","be","been","have","has"
        }
        kws = set(re.findall(r"\w+", question.lower())) - stop
        scored_kw = []
        for chunk in self._chunks:
            words = set(re.findall(r"\w+", chunk["text"].lower()))
            hits  = len(kws & words)
            if hits:
                scored_kw.append((chunk["doc_name"], chunk["text"],
                                  hits / max(len(kws), 1)))
        scored_kw.sort(key=lambda x: x[2], reverse=True)
        if scored_kw:
            return self._format_context(scored_kw[:top_k])

        return ""

    def _format_context(self, results: List[Tuple]) -> str:
        parts = []
        for i, (doc_name, text, score) in enumerate(results, 1):
            parts.append(f"[Source: {doc_name} | chunk {i}]\n{text.strip()}")
        return "\n\n---\n\n".join(parts)

    # ── Info ──────────────────────────────────────────────
    def doc_count(self) -> int:
        return len(self._docs)

    def list_docs(self) -> List[str]:
        return [
            f"{v['name']}  ({v['n_chunks']} chunks)"
            for v in self._docs.values()
        ]