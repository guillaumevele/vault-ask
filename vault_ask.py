#!/usr/bin/env python3
"""vault-ask — Ask your Obsidian vault, get cited answers, never hallucinate.

A tiny, dependency-free grounded question-answering tool over a Markdown
knowledge base (built for Obsidian, works on any folder of .md files).

How it works:
  1. Fast candidate selection with ripgrep over the whole vault.
  2. Notes are ranked by IDF coverage — rare, specific terms (e.g. a project
     codename) outweigh ubiquitous ones (e.g. a word in hundreds of notes).
  3. Query-focused excerpts of the top notes are sent to your LLM with a strict
     prompt: every claim MUST cite its source note as a [[wikilink]], and if the
     excerpts don't answer the question the model MUST refuse instead of guessing.
  4. A robust refusal check guarantees a refusal is never dressed up as a
     sourced answer.

The LLM is whatever command you configure via $VAULT_ASK_LLM, so it works with a
local model (Ollama), a CLI like `llm`, or any subscription CLI you already use.
Nothing leaves your machine except what your own LLM command sends.

Usage:
    export VAULT_ASK_LLM='ollama run llama3.1'        # or 'llm -m gpt-4o-mini', etc.
    vault_ask.py --vault ~/Obsidian/MyVault "what did I decide about pricing?"

Requires: Python 3.9+, ripgrep (`rg`) on PATH.
License: MIT.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

__version__ = "0.1.1"

REFUSAL = "No note in the vault answers this question."

# Directories that are noise, not knowledge — skipped during candidate search.
DEFAULT_EXCLUDED_DIRS = (".obsidian", ".trash", ".git", "node_modules")

# Stop / question / function words (EN + FR): noise for keyword candidate search.
STOPWORDS = {
    # English
    "what", "which", "where", "when", "why", "how", "who", "whom", "whose",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "for", "with", "from", "into",
    "about", "that", "this", "these", "those", "and", "or", "but", "not",
    "you", "your", "yours", "my", "mine", "our", "their", "its", "his", "her",
    "can", "could", "should", "would", "will", "shall", "may", "might", "must",
    "get", "got", "make", "made", "any", "some", "all", "more", "most", "than",
    # French
    "quel", "quels", "quelle", "quelles", "pourquoi", "comment", "quand",
    "qui", "quoi", "est", "sont", "etait", "etre", "avoir", "faut", "fait",
    "faire", "pour", "avec", "dans", "sur", "sous", "par", "des", "les",
    "une", "mon", "mes", "ton", "tes", "son", "ses", "nos", "vos", "leur",
    "leurs", "que", "dont", "cette", "cet", "ces", "celle", "celui", "donc",
    "alors", "ainsi", "aussi", "plus", "moins", "tout", "tous", "toute",
    "toutes", "deja", "encore", "vraiment", "bien", "retenu", "retenue",
}


def normalize(text: str) -> str:
    """Lowercase + strip accents (NFKD) for accent/case-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


def query_terms(query: str, min_len: int = 3) -> list[str]:
    """Content terms of the query: tokens >= min_len that are not stopwords."""
    tokens = re.split(r"[^a-z0-9]+", normalize(query))
    return [t for t in tokens if len(t) >= min_len and t not in STOPWORDS]


def _vault_root(vault: Path) -> Path:
    return vault.expanduser().resolve()


def obsidian_link(vault: Path, path: Path) -> str:
    """Obsidian-style [[relative/path|title]] link to a note."""
    try:
        rel = path.resolve().relative_to(_vault_root(vault))
    except ValueError:
        rel = Path(path.name)
    return f"[[{rel.with_suffix('')}|{path.stem}]]"


def note_excerpt(path: Path, terms: list[str], max_chars: int = 650, context: int = 1) -> str:
    """Query-focused excerpt: headings + lines mentioning a term, plus a small
    context window around each match (notes can be long, and a matched keyword's
    answer often sits on the neighbouring wrapped line)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    lines = text.splitlines()
    keep_idx: set[int] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        norm = normalize(line)
        if stripped.startswith("#") or any(term in norm for term in terms):
            for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                keep_idx.add(j)
    kept = [lines[i].strip() for i in sorted(keep_idx) if lines[i].strip()]
    body = "\n".join(kept) if kept else "\n".join(
        l.strip() for l in lines if l.strip()
    )
    return body[:max_chars]


def candidate_notes(
    vault: Path,
    query: str,
    limit: int = 5,
    excluded_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS,
    timeout_s: int = 20,
) -> list[dict]:
    """Select the most relevant notes via ripgrep, ranked by IDF coverage.

    A note that contains rare, specific query terms ranks above a note merely
    dense in a ubiquitous term, so the discriminating words decide relevance.
    """
    root = _vault_root(vault)
    terms = query_terms(query)
    if not terms or not root.is_dir():
        return []
    excludes: list[str] = []
    for name in excluded_dirs:
        excludes += ["-g", f"!{name}/**", "-g", f"!{name}"]

    term_files: dict[str, dict[str, int]] = {}
    for term in terms:
        try:
            proc = subprocess.run(
                ["rg", "-c", "-i", "--glob", "*.md", *excludes, "--", term, str(root)],
                capture_output=True, text=True, timeout=timeout_s,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode not in (0, 1):  # 1 = no matches, fine
            continue
        files: dict[str, int] = {}
        for raw in proc.stdout.splitlines():
            path, _, count = raw.rpartition(":")
            path = path.strip()
            if not path:
                continue
            try:
                files[path] = int(count)
            except ValueError:
                files[path] = 1
        if files:
            term_files[term] = files
    if not term_files:
        return []

    all_paths: set[str] = set()
    for files in term_files.values():
        all_paths |= set(files.keys())
    total = max(len(all_paths), 1)

    coverage: dict[str, set] = {}
    idf_coverage: dict[str, float] = {}  # sum of idf over DISTINCT terms matched
    tf_score: dict[str, float] = {}      # tf*idf, tie-breaker
    for term, files in term_files.items():
        idf = math.log((total + 1) / (len(files) + 1)) + 1.0
        for path, tf in files.items():
            coverage.setdefault(path, set()).add(term)
            idf_coverage[path] = idf_coverage.get(path, 0.0) + idf
            tf_score[path] = tf_score.get(path, 0.0) + min(tf, 8) * idf

    ranked = sorted(
        idf_coverage,
        key=lambda p: (idf_coverage[p], tf_score[p]),
        reverse=True,
    )
    notes: list[dict] = []
    for path_str in ranked[:limit]:
        path = Path(path_str)
        notes.append({
            "file": str(path),
            "title": path.stem,
            "link": obsidian_link(vault, path),
            "excerpt": note_excerpt(path, terms),
            "matched_terms": sorted(coverage[path_str]),
        })
    return notes


def build_prompt(query: str, notes: list[dict]) -> str:
    """Grounded prompt: mandatory [[citations]], explicit refusal if unsupported."""
    blocks = []
    for note in notes:
        excerpt = (note.get("excerpt") or "").strip()
        if not excerpt:
            continue
        blocks.append(f"[Source: {note['link']}]\n{excerpt}")
    sources = "\n\n---\n\n".join(blocks)
    return (
        "You answer questions strictly from a personal Markdown knowledge base.\n"
        "Use ONLY the note excerpts below. Absolute rules, no exceptions:\n"
        "1. Every claim MUST be followed by its source as a [[link]], copied "
        "EXACTLY from the 'Source:' line.\n"
        "2. Invent nothing; add no outside knowledge.\n"
        f"3. If the excerpts do not answer the question, reply with EXACTLY this "
        f"and nothing else: {REFUSAL}\n"
        "4. Be concise and factual: at most 3 lines, no preamble.\n\n"
        f"QUESTION: {query}\n\n"
        f"EXCERPTS:\n{sources}"
    )


def is_refusal(text: str) -> bool:
    """Robust refusal detection (punctuation/case/accent insensitive). A refusal
    must never be mistaken for a sourced answer."""
    norm = normalize(text).strip().rstrip(".").strip()
    target = normalize(REFUSAL).strip().rstrip(".").strip()
    return bool(norm) and norm == target


def run_llm(prompt: str, *, command: str | None = None, timeout_s: int = 120) -> str | None:
    """Run the configured LLM command. If the command contains '{prompt}' the
    prompt is substituted as an argument, otherwise it is piped via stdin.
    Returns the text answer, or None on any failure (caller falls back)."""
    command = command or os.environ.get("VAULT_ASK_LLM", "").strip()
    if not command:
        return None
    try:
        if "{prompt}" in command:
            full = command.replace("{prompt}", shlex.quote(prompt))
            proc = subprocess.run(
                full, shell=True, capture_output=True, text=True, timeout=timeout_s,
            )
        else:
            proc = subprocess.run(
                shlex.split(command), input=prompt,
                capture_output=True, text=True, timeout=timeout_s,
            )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def ripgrep_available() -> bool:
    return shutil.which("rg") is not None


def ask(
    vault: Path,
    query: str,
    limit: int = 5,
    command: str | None = None,
    sources_only: bool = False,
) -> dict:
    """Grounded Q&A over the vault. Always returns a structured result; a missing
    LLM or zero candidates yields an honest refusal, never a fabricated answer.
    With sources_only=True, returns the ranked relevant notes and skips the LLM."""
    query = re.sub(r"\s+", " ", str(query or "").strip())
    if not query:
        return {"ok": False, "reason": "empty-query"}
    if not ripgrep_available():
        return {"ok": False, "reason": "ripgrep-not-found"}
    notes = candidate_notes(vault, query, limit=limit)
    result = {
        "ok": True,
        "query": query,
        "candidates": [{"title": n["title"], "link": n["link"]} for n in notes],
    }
    if sources_only:
        result["answer"] = None
        result["grounded"] = False
        result["sources"] = [n["link"] for n in notes]
        result["mode"] = "sources-only"
        return result
    if not notes:
        result["answer"] = REFUSAL
        result["grounded"] = False
        result["sources"] = []
        return result
    text = run_llm(build_prompt(query, notes), command=command)
    if not text:
        result["answer"] = None
        result["grounded"] = False
        result["sources"] = []
        result["reason"] = "no-llm"
        return result
    refused = is_refusal(text)
    result["answer"] = REFUSAL if refused else text
    result["grounded"] = not refused
    result["sources"] = [] if refused else [n["link"] for n in notes]
    return result


def format_result(result: dict) -> str:
    if not result.get("ok"):
        reason = result.get("reason", "error")
        if reason == "ripgrep-not-found":
            return (
                "vault-ask: ripgrep (`rg`) was not found on your PATH.\n"
                "Install it: https://github.com/BurntSushi/ripgrep#installation"
            )
        if reason == "empty-query":
            return "vault-ask: please provide a question."
        return f"vault-ask: {reason}"
    cands = result.get("candidates") or []
    if result.get("mode") == "sources-only":
        lines = [f"Most relevant notes for: {result['query']}", ""]
        lines += [f"- {c['link']}" for c in cands] or ["(no matching notes)"]
        return "\n".join(lines)
    lines = [f"Q: {result['query']}", ""]
    if result.get("answer"):
        lines.append(result["answer"])
    elif result.get("reason") == "no-llm":
        lines.append(
            "(No LLM configured or it failed — set $VAULT_ASK_LLM, "
            "or use --sources-only. Relevant notes below.)"
        )
    if cands:
        lines += ["", "Notes consulted:"]
        lines += [f"- {c['link']}" for c in cands]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask your Obsidian vault, get cited answers, never hallucinate.",
    )
    parser.add_argument("question", nargs="*", help="your question")
    parser.add_argument(
        "--vault",
        default=os.environ.get("OBSIDIAN_VAULT", "."),
        help="path to the vault (default: $OBSIDIAN_VAULT or current dir)",
    )
    parser.add_argument("--limit", type=int, default=5, help="max notes to consult")
    parser.add_argument(
        "--llm", default=None,
        help="LLM command (default: $VAULT_ASK_LLM). Use '{prompt}' for arg-style.",
    )
    parser.add_argument(
        "--sources-only", action="store_true",
        help="just list the most relevant notes, no LLM call (a smart grep for your vault)",
    )
    parser.add_argument("--json", action="store_true", help="output raw JSON")
    parser.add_argument("--version", action="version", version=f"vault-ask {__version__}")
    args = parser.parse_args(argv)

    question = " ".join(args.question).strip()
    if not question:
        parser.error("provide a question")
    result = ask(
        Path(args.vault), question,
        limit=args.limit, command=args.llm, sources_only=args.sources_only,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_result(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
