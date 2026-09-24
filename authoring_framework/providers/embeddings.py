"""Text embeddings for retrieval — direct OpenAI, with a content-keyed disk cache.

One primitive: `embed(texts) -> [vector, ...] | None`. Used by `skills.retrieve` to score
the gesture-recipe docs against a topic semantically instead of by keyword overlap.

OpenAI's own embeddings endpoint (`OA_OPENAI_KEY` / `OPENAI_API_KEY`), independent of which
chat provider the run drives — the recipe retrieval must score the same way whatever model
is being benchmarked. The endpoint is pinned (a stray $OPENAI_BASE_URL is ignored). No key — or any
API failure — returns None, and the caller falls back to its keyword scorer; retrieval must
never take a run down.

The disk cache is keyed by (model, text) content hash, so doc embeddings are paid ONCE per
doc revision across all runs — a lookup's marginal cost is embedding the query string.
"""
import hashlib
import json
import os
from pathlib import Path

from .. import config  # noqa: F401  (imported for its load_dotenv side effect)

# Small and cheap; the recipe surface is one name + one sentence per doc, so a bigger
# embedding model buys nothing. $EMBED_MODEL overrides — the cache key carries the model,
# so switching never serves stale vectors.
EMBED_MODEL = os.getenv("EMBED_MODEL") or "text-embedding-3-small"

_KEY_ENVS = ("OA_OPENAI_KEY", "OPENAI_API_KEY")

_CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "embeddings.json"

_cache = None          # hash -> vector, loaded once per process
_dead = False          # first API failure disables embeddings for the process (the caller's
                       # keyword fallback is deterministic; flapping between scorers is worse)


def _key():
    return next((os.getenv(k) for k in _KEY_ENVS if os.getenv(k)), None)


def available():
    """True when embeddings can be attempted (a direct OpenAI key is set and no call has
    failed yet this process)."""
    return bool(_key()) and not _dead


def _h(text):
    return hashlib.sha1(f"{EMBED_MODEL}\x00{text}".encode("utf-8")).hexdigest()


def _load_cache():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache():
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache), encoding="utf-8")
    except Exception:
        pass                                     # a read-only disk must not break retrieval


def embed(texts):
    """Embedding vectors for `texts` (order preserved), or None when unavailable/failed.
    Cached texts cost nothing; only the misses go to the API, in one batched call."""
    global _dead
    if not _key() or _dead:
        return None
    if not texts:
        return []
    cache = _load_cache()
    missing = [t for t in texts if _h(t) not in cache]
    if missing:
        try:
            from openai import OpenAI
            resp = OpenAI(api_key=_key(), base_url="https://api.openai.com/v1").embeddings.create(
                model=EMBED_MODEL, input=missing)
            for t, d in zip(missing, resp.data):
                cache[_h(t)] = d.embedding
            _save_cache()
        except Exception as e:
            _dead = True
            print(f"[embeddings] {type(e).__name__}: {e} — keyword fallback for this process")
            return None
    return [cache[_h(t)] for t in texts]


def cosine(a, b):
    """Cosine similarity of two vectors (plain floats — no numpy dependency here)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
