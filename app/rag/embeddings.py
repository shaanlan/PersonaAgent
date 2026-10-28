from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbedding:
    """Deterministic hash embedding (design-compatible stand-in for bge-m3).

    Not semantically meaningful, but stable, fast, and dimension-correct so the
    full embed -> store -> query pipeline runs without external services.
    """

    name = "mock"

    def __init__(self, model: str = "mock-hash", dim: int = 1024) -> None:
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _tokenize(text)
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 if token.isascii() else 0.6)
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class OllamaEmbedding:
    name = "ollama"

    def __init__(self, model: str, dim: int, base_url: str) -> None:
        self.model = model
        self.dim = dim
        self.base_url = base_url.rstrip("/")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts})
            response.raise_for_status()
            payload = response.json()
        vectors = payload.get("embeddings") or []
        if len(vectors) != len(texts):
            raise RuntimeError("embedding count mismatch")
        return [[float(v) for v in row] for row in vectors]


class OpenAICompatibleEmbedding:
    name = "openai_compatible"

    def __init__(self, model: str, dim: int, base_url: str, api_key: str = "") -> None:
        self.model = model
        self.dim = dim
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        items = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        return [[float(v) for v in item["embedding"]] for item in items]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "ollama":
        return OllamaEmbedding(settings.embedding_model, settings.embedding_dim, settings.embedding_api_base)
    if provider == "openai_compatible":
        return OpenAICompatibleEmbedding(
            settings.embedding_model,
            settings.embedding_dim,
            settings.embedding_api_base,
            settings.embedding_api_key,
        )
    return MockEmbedding(settings.embedding_model, settings.embedding_dim)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def embedding_config() -> dict[str, Any]:
    get_settings()
    provider = get_embedding_provider()
    return {"provider": provider.name, "model": provider.model, "dim": provider.dim}
