"""Embeddings package for generating vector representations of text."""

from .base import BatchingEmbedder, CachingEmbedder, Embedder, EmbeddingResult
from .bm25 import BM25Embedder
from .openai import OpenAIEmbedder
from .registry import EmbedderRegistry

__all__ = [
    "Embedder",
    "EmbeddingResult",
    "CachingEmbedder",
    "BatchingEmbedder",
    "BM25Embedder",
    "OpenAIEmbedder",
    "EmbedderRegistry",
]
