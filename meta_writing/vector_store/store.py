"""ChromaDB + BGE-M3 vector store for semantic chapter retrieval.

Stores chapter text chunked by scene (~500-1000 Chinese characters per chunk).
Supports:
- Adding/updating chapter chunks
- Semantic search ("find the chapter where X happened")
- Re-embedding revised chapters (old chunks replaced)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


# Chunk size targets (in Chinese characters)
CHUNK_MIN_SIZE = 300
CHUNK_TARGET_SIZE = 700
CHUNK_MAX_SIZE = 1200


class ChapterVectorStore:
    """Vector store for chapter semantic retrieval using ChromaDB + BGE-M3."""

    def __init__(
        self,
        persist_dir: str | Path,
        collection_name: str = "chapters",
        embedding_model: str = "BAAI/bge-m3",
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model_name = embedding_model
        self._embedding_fn: Any = None

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def embedding_fn(self) -> Any:
        """Lazy-load the embedding model (BGE-M3 requires ~2.2GB VRAM)."""
        if self._embedding_fn is None:
            from sentence_transformers import SentenceTransformer
            self._embedding_fn = SentenceTransformer(self.embedding_model_name)
        return self._embedding_fn

    def add_chapter(self, chapter_number: int, text: str) -> int:
        """Add a chapter's text to the vector store, chunked by scene.

        Returns the number of chunks created.
        """
        chunks = chunk_chapter(text)
        if not chunks:
            return 0

        ids = [f"ch{chapter_number:03d}_chunk{i:03d}" for i in range(len(chunks))]
        metadatas = [
            {"chapter": chapter_number, "chunk_index": i, "chunk_count": len(chunks)}
            for i in range(len(chunks))
        ]

        embeddings = self.embedding_fn.encode(chunks, normalize_embeddings=True).tolist()

        self.collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(chunks)

    def update_chapter(self, chapter_number: int, text: str) -> int:
        """Re-embed a revised chapter. Removes old chunks first.

        Returns the number of new chunks created.
        """
        self.remove_chapter(chapter_number)
        return self.add_chapter(chapter_number, text)

    def remove_chapter(self, chapter_number: int) -> None:
        """Remove all chunks for a chapter."""
        # Query for all chunks with this chapter number
        results = self.collection.get(
            where={"chapter": chapter_number},
        )
        if results["ids"]:
            self.collection.delete(ids=results["ids"])

    def query(self, query_text: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Semantic search across all chapters.

        Returns list of dicts with keys: text, chapter, chunk_index, distance.
        """
        if self.collection.count() == 0:
            return []

        embedding = self.embedding_fn.encode([query_text], normalize_embeddings=True).tolist()

        results = self.collection.query(
            query_embeddings=embedding,
            n_results=min(n_results, self.collection.count()),
        )

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "text": results["documents"][0][i],
                "chapter": results["metadatas"][0][i]["chapter"],
                "chunk_index": results["metadatas"][0][i]["chunk_index"],
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return output

    def chapter_count(self) -> int:
        """Number of unique chapters in the store."""
        if self.collection.count() == 0:
            return 0
        all_meta = self.collection.get()["metadatas"]
        chapters = {m["chapter"] for m in all_meta if m}
        return len(chapters)


def chunk_chapter(text: str) -> list[str]:
    """Split chapter text into scene-based chunks.

    Strategy:
    1. Split on scene breaks (blank lines, scene separators like --- or ***)
    2. If a scene is too long, split on paragraph breaks
    3. Merge short scenes into adjacent chunks
    """
    if not text or not text.strip():
        return []

    # Split on scene separators (*** / --- / ——— with surrounding whitespace/newlines)
    scene_pattern = r"\n\s*\n\s*(?:[*]{3,}|[-]{3,}|[—]{3,})\s*\n\s*\n|\n\s*\n\s*\n"
    raw_scenes = re.split(scene_pattern, text)
    raw_scenes = [s.strip() for s in raw_scenes if s.strip()]

    if not raw_scenes:
        return [text.strip()] if text.strip() else []

    # Split oversized scenes on paragraph breaks
    scenes: list[str] = []
    for scene in raw_scenes:
        if len(scene) <= CHUNK_MAX_SIZE:
            scenes.append(scene)
        else:
            paragraphs = re.split(r"\n\s*\n", scene)
            current = ""
            for para in paragraphs:
                if len(current) + len(para) > CHUNK_TARGET_SIZE and current:
                    scenes.append(current.strip())
                    current = para
                else:
                    current = current + "\n\n" + para if current else para
            if current.strip():
                scenes.append(current.strip())

    # Merge short scenes
    chunks: list[str] = []
    current = ""
    for scene in scenes:
        if len(current) + len(scene) < CHUNK_MIN_SIZE:
            current = current + "\n\n" + scene if current else scene
        else:
            if current:
                chunks.append(current.strip())
            current = scene
    if current.strip():
        chunks.append(current.strip())

    return chunks
