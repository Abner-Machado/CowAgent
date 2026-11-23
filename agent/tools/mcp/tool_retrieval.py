# encoding:utf-8
"""
On-demand MCP tool retrieval.

Pure, stateless selection helpers used by the streaming executor to decide
which MCP tools to inject into a given LLM turn. Vector precompute + caching
live in ToolManager (the tool-lifecycle owner, a process-wide singleton);
only the context-aware selection lives here, because only the executor knows
the conversation context.

Invariants (per maintainer review of the feature proposal):
  * Built-in tools are never handled here — the caller injects them in full.
  * The legacy selector returns None on any failure / missing input so the
    caller falls back to full injection; tools must never be silently dropped.
    The metadata selector represents the same fallback as a decision with a
    ``fallback_reason``.
  * Selection is union-accumulated across turns by the caller (only-grows),
    so a tool that already produced a tool_use in the message history can
    never disappear from the schema mid-run (which would make Claude/MiniMax
    raise a message-format error).
"""
from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Sequence, Set, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# How many trailing messages to concatenate into the retrieval query. Tool
# needs drift across a multi-turn tool-call loop, so a single (initial) user
# query is not enough; a short recent window captures the drift without
# bloating the query with stale context.
DEFAULT_QUERY_MESSAGES = 5


@dataclass(frozen=True)
class McpRetrievalDecision:
    """Metadata for one MCP tool retrieval decision.

    ``selected`` is the accumulated tool set to inject. ``ranked`` contains the
    current turn's similarity ranking, without query text or raw vectors.
    """
    selected: Set[str]
    ranked: List[Tuple[str, float]]
    candidate_count: int
    fallback_reason: Optional[str] = None


def build_retrieval_query(messages: list, max_messages: int = DEFAULT_QUERY_MESSAGES) -> str:
    """Concatenate the text of the most recent messages into a retrieval query.

    Only ``text`` content blocks are kept; ``tool_use`` / ``tool_result`` blocks
    are skipped so the query stays short and focused on natural-language intent
    rather than large serialized tool payloads.

    Args:
        messages: Claude-style message list, each ``{"role", "content"}`` where
            content is either a string or a list of typed blocks.
        max_messages: Size of the trailing window to consider.

    Returns:
        A single string (possibly empty if no text is found).
    """
    if not messages:
        return ""

    parts: List[str] = []
    for message in messages[-max_messages:]:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            if content.strip():
                parts.append(content.strip())
            continue
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
    return "\n".join(parts)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 on degenerate input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def select_mcp_tools(
    query_vector: Optional[Sequence[float]],
    tool_vectors: Dict[str, Sequence[float]],
    top_k: int,
    already_selected: Optional[Set[str]] = None,
) -> Optional[Set[str]]:
    """Return the accumulated set of MCP tool names to inject this turn.

    Computes cosine similarity between ``query_vector`` and each candidate
    tool vector, keeps the ``top_k`` best, and unions them with
    ``already_selected`` so the injected set only ever grows within a run.

    Args:
        query_vector: Embedding of the current retrieval query, or None.
        tool_vectors: ``{mcp_tool_name: vector}`` for candidate MCP tools.
        top_k: Max number of tools to add from this turn's ranking.
        already_selected: Names accumulated in previous turns of this run.

    Returns:
        The union set of tool names to inject, or None to signal
        "fall back to full injection" (no query vector, empty/invalid index,
        or any unexpected error). This function never raises.
    """
    decision = select_mcp_tools_with_metadata(
        query_vector,
        tool_vectors,
        top_k,
        already_selected,
    )
    if decision is None or decision.fallback_reason is not None:
        return None
    return decision.selected


def _is_finite_vector(vector: Sequence[float]) -> bool:
    """Return whether every vector value is a finite number."""
    try:
        return all(math.isfinite(float(value)) for value in vector)
    except (TypeError, ValueError):
        return False


def select_mcp_tools_with_metadata(
    query_vector: Optional[Sequence[float]],
    tool_vectors: Dict[str, Sequence[float]],
    top_k: int,
    already_selected: Optional[Set[str]] = None,
) -> Optional[McpRetrievalDecision]:
    """Return MCP retrieval selection plus metadata for observability.

    A decision with ``fallback_reason`` set describes a safe full-injection
    fallback. The legacy ``select_mcp_tools`` wrapper converts that decision
    back to ``None`` so existing callers keep their current behavior.
    """
    accumulated: Set[str] = set(already_selected) if already_selected else set()

    try:
        if query_vector is None:
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="missing_query_vector",
            )
        if len(query_vector) == 0:
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="missing_query_vector",
            )
        if not _is_finite_vector(query_vector):
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="invalid_query_vector",
            )
        if not tool_vectors:
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="empty_tool_index",
            )
        if top_k <= 0:
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="invalid_top_k",
            )

        expected_dim = len(query_vector)
        # Only rank candidates whose vector dimensionality matches the query.
        # A dimension mismatch means the index was built with a different
        # embedding model; ranking across dims is meaningless.
        candidates = {}
        for name, vec in tool_vectors.items():
            try:
                if (
                    vec is not None
                    and len(vec) > 0
                    and len(vec) == expected_dim
                    and _is_finite_vector(vec)
                ):
                    candidates[name] = vec
            except (TypeError, ValueError):
                continue
        if not candidates:
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="no_compatible_candidates",
            )

        ranked = _rank_by_similarity(query_vector, candidates)
        if not all(math.isfinite(float(score)) for _name, score in ranked):
            return McpRetrievalDecision(
                selected=accumulated,
                ranked=[],
                candidate_count=0,
                fallback_reason="non_finite_score",
            )
        accumulated.update(name for name, _score in ranked[:top_k])
        return McpRetrievalDecision(
            selected=accumulated,
            ranked=ranked,
            candidate_count=len(candidates),
        )
    except Exception:
        # Selection must never break the agent — fall back to full injection.
        return McpRetrievalDecision(
            selected=accumulated,
            ranked=[],
            candidate_count=0,
            fallback_reason="selection_error",
        )


def _rank_by_similarity(
    query_vector: Sequence[float],
    candidates: Dict[str, Sequence[float]],
) -> List[tuple]:
    """Return ``[(name, score), ...]`` sorted by descending cosine similarity.

    Uses numpy when available (vectorized, matching the memory-search path),
    with a pure-Python fallback so the feature works without numpy installed.
    """
    names = list(candidates.keys())

    if _HAS_NUMPY:
        matrix = np.array([candidates[n] for n in names], dtype=np.float32)  # (N, D)
        q_vec = np.array(query_vector, dtype=np.float32)                     # (D,)
        dots = matrix @ q_vec                                                # (N,)
        row_norms = np.linalg.norm(matrix, axis=1)                          # (N,)
        q_norm = float(np.linalg.norm(q_vec))
        denominators = row_norms * q_norm
        np.maximum(denominators, 1e-10, out=denominators)                   # avoid div-by-zero
        sims = dots / denominators
        order = np.argsort(sims)[::-1]
        return [(names[i], float(sims[i])) for i in order]

    scored = [(n, cosine_similarity(query_vector, candidates[n])) for n in names]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
