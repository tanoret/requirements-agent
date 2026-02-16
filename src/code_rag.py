from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    path: str
    start_line: int
    end_line: int
    score: float
    text: str


class CodebaseRAG:
    """
    A lightweight, dependency-free retrieval layer over the repo codebase using BM25.

    Intended use:
      - Ground an LLM on "what the current code does"
      - Answer developer questions ("How does applicability.when work?")
      - Provide schema-field context ("What are ValveProfile required fields?")

    Notes:
      - This is NOT embedding-based. It's BM25 lexical retrieval.
      - Works well for codebases and JSON schemas because key tokens repeat.
    """

    def __init__(
        self,
        repo_root: Path,
        include_globs: Sequence[str] | None = None,
        exclude_globs: Sequence[str] | None = None,
        max_lines_per_chunk: int = 120,
        overlap_lines: int = 20,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.include_globs = include_globs or [
            "README.md",
            "src/**/*.py",
            "schemas/**/*.json",
            "tests/**/*.py",
        ]
        self.exclude_globs = exclude_globs or [
            "src/**/__pycache__/**",
            "tests/**/__pycache__/**",
            "data/**/*.json",  # usually large; keep it out of "code RAG" by default
            "demo/out/**",
            "examples/**",
        ]

        self.max_lines_per_chunk = max_lines_per_chunk
        self.overlap_lines = overlap_lines

        self._chunks: List[Chunk] = []
        self._chunk_tokens: List[List[str]] = []
        self._doc_freq: Dict[str, int] = {}
        self._avgdl: float = 0.0

        self._build_index()

    def _iter_files(self) -> List[Path]:
        paths: List[Path] = []
        for pattern in self.include_globs:
            paths.extend(self.repo_root.glob(pattern))

        # Apply exclusions
        excluded: set[Path] = set()
        for pattern in self.exclude_globs:
            excluded.update(self.repo_root.glob(pattern))

        uniq: List[Path] = []
        seen: set[Path] = set()
        for p in paths:
            p = p.resolve()
            if p in excluded:
                continue
            if not p.is_file():
                continue
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        return sorted(uniq)

    def _chunk_file(self, path: Path) -> List[Chunk]:
        rel = str(path.relative_to(self.repo_root))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if not lines:
            return []

        chunks: List[Chunk] = []
        step = max(1, self.max_lines_per_chunk - self.overlap_lines)

        for i in range(0, len(lines), step):
            start = i
            end = min(len(lines), i + self.max_lines_per_chunk)
            chunk_text = "\n".join(lines[start:end])
            chunks.append(Chunk(path=rel, start_line=start + 1, end_line=end, text=chunk_text))
            if end == len(lines):
                break

        return chunks

    def _build_index(self) -> None:
        files = self._iter_files()
        chunks: List[Chunk] = []
        for f in files:
            chunks.extend(self._chunk_file(f))

        self._chunks = chunks
        self._chunk_tokens = [_tokenize(c.text) for c in chunks]

        # document frequency
        df: Dict[str, int] = {}
        total_len = 0
        for toks in self._chunk_tokens:
            total_len += len(toks)
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._doc_freq = df
        self._avgdl = (total_len / len(self._chunk_tokens)) if self._chunk_tokens else 0.0

    def _idf(self, term: str) -> float:
        """
        BM25 IDF with +1 inside log to avoid negative values on frequent tokens.
        """
        N = len(self._chunk_tokens) or 1
        df = self._doc_freq.get(term, 0)
        return math.log(1.0 + (N - df + 0.5) / (df + 0.5))

    def retrieve(self, query: str, k: int = 6, k1: float = 1.5, b: float = 0.75) -> List[RetrievedChunk]:
        q = _tokenize(query)
        if not q or not self._chunk_tokens:
            return []

        # term -> idf
        idf = {t: self._idf(t) for t in set(q)}

        scores: List[Tuple[int, float]] = []
        for idx, doc in enumerate(self._chunk_tokens):
            if not doc:
                continue
            dl = len(doc)
            # term frequencies in doc for query terms only
            tf: Dict[str, int] = {t: 0 for t in q}
            for t in doc:
                if t in tf:
                    tf[t] += 1

            score = 0.0
            for term, freq in tf.items():
                if freq <= 0:
                    continue
                denom = freq + k1 * (1.0 - b + b * (dl / (self._avgdl or 1.0)))
                score += idf.get(term, 0.0) * (freq * (k1 + 1.0)) / denom

            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        out: List[RetrievedChunk] = []
        for idx, score in scores[:k]:
            c = self._chunks[idx]
            out.append(RetrievedChunk(path=c.path, start_line=c.start_line, end_line=c.end_line, score=score, text=c.text))
        return out
