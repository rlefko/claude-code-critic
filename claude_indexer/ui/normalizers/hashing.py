"""Hashing utilities for near-duplicate detection.

This module provides locality-sensitive hashing algorithms for detecting
near-duplicate styles and components. SimHash and MinHash are used to
efficiently find similar items even when they differ slightly.
"""

import hashlib
import random
from collections.abc import Sequence


def compute_simhash(features: Sequence[str], hash_bits: int = 64) -> str:
    """Compute SimHash for near-duplicate detection.

    SimHash is a locality-sensitive hash that produces similar hashes
    for similar inputs. It works by:
    1. Hashing each feature
    2. For each bit position, sum +1 for 1s and -1 for 0s
    3. Final hash has 1 where sum > 0, 0 otherwise

    Args:
        features: Sequence of feature strings to hash.
        hash_bits: Number of bits in the output hash (default 64).

    Returns:
        Hex string representation of the SimHash.
    """
    if not features:
        return "0" * (hash_bits // 4)  # Return zero hash for empty

    # Initialize vector with zeros
    v = [0] * hash_bits

    for feature in features:
        # Get hash of feature
        feature_hash = int(hashlib.md5(feature.encode()).hexdigest(), 16)

        # Update vector based on hash bits
        for i in range(hash_bits):
            if (feature_hash >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    # Generate final hash
    result = 0
    for i in range(hash_bits):
        if v[i] > 0:
            result |= 1 << i

    return format(result, f"0{hash_bits // 4}x")


def simhash_similarity(hash1: str, hash2: str) -> float:
    """Compute similarity between two SimHashes (0-1 scale).

    Uses Hamming distance to measure similarity. Two identical hashes
    have similarity 1.0, completely different hashes approach 0.0.

    Args:
        hash1: First SimHash as hex string.
        hash2: Second SimHash as hex string.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    if not hash1 or not hash2:
        return 0.0

    if hash1 == hash2:
        return 1.0

    int1 = int(hash1, 16)
    int2 = int(hash2, 16)

    # XOR to find differing bits
    diff = int1 ^ int2

    # Count differing bits (Hamming distance)
    distance = bin(diff).count("1")

    # Convert to similarity (1 - normalized distance)
    total_bits = len(hash1) * 4
    return 1.0 - (distance / total_bits)


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex hashes.

    Args:
        hash1: First hash as hex string.
        hash2: Second hash as hex string.

    Returns:
        Number of differing bits.
    """
    if not hash1 or not hash2:
        return max(len(hash1), len(hash2)) * 4

    int1 = int(hash1, 16)
    int2 = int(hash2, 16)

    diff = int1 ^ int2
    return bin(diff).count("1")


def compute_minhash(
    features: Sequence[str],
    num_permutations: int = 128,
    seed: int = 42,
) -> list[int]:
    """Compute MinHash signature for set similarity.

    MinHash estimates Jaccard similarity between sets by hashing
    each element with multiple hash functions and keeping the minimum.

    Args:
        features: Sequence of feature strings to hash.
        num_permutations: Number of hash permutations (signature length).
        seed: Random seed for reproducible hash functions.

    Returns:
        List of minimum hash values (the signature).
    """
    if not features:
        return [0] * num_permutations

    # Use deterministic random seed for reproducibility
    rng = random.Random(seed)

    # Generate hash coefficients for universal hashing: (a*x + b) mod p
    max_val = 2**32 - 1
    prime = 4294967311  # Large prime > max_val
    a_coeffs = [rng.randint(1, max_val) for _ in range(num_permutations)]
    b_coeffs = [rng.randint(0, max_val) for _ in range(num_permutations)]

    signature = [float("inf")] * num_permutations

    for feature in features:
        # Hash the feature to a 32-bit integer
        h = int(hashlib.md5(feature.encode()).hexdigest()[:8], 16)

        # Update signature with minimum values for each permutation
        for i in range(num_permutations):
            # Universal hash function
            perm_hash = (a_coeffs[i] * h + b_coeffs[i]) % prime
            signature[i] = min(signature[i], perm_hash)

    return [int(s) if s != float("inf") else 0 for s in signature]


def minhash_similarity(sig1: list[int], sig2: list[int]) -> float:
    """Estimate Jaccard similarity from MinHash signatures.

    The fraction of matching signature positions estimates the
    Jaccard similarity of the original sets.

    Args:
        sig1: First MinHash signature.
        sig2: Second MinHash signature.

    Returns:
        Estimated Jaccard similarity between 0.0 and 1.0.

    Raises:
        ValueError: If signatures have different lengths.
    """
    if len(sig1) != len(sig2):
        raise ValueError("Signatures must have same length")

    if not sig1:
        return 0.0

    matches = sum(1 for a, b in zip(sig1, sig2, strict=False) if a == b)
    return matches / len(sig1)


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute exact Jaccard similarity between two sets.

    Jaccard = |A ∩ B| / |A ∪ B|

    Args:
        set1: First set of strings.
        set2: Second set of strings.

    Returns:
        Jaccard similarity between 0.0 and 1.0.
    """
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content.

    Used for exact duplicate detection.

    Args:
        content: String content to hash.

    Returns:
        SHA256 hex digest.
    """
    return hashlib.sha256(content.encode()).hexdigest()
