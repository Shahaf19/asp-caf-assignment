"""Merge functionality for libcaf."""

from enum import Enum, auto
from pathlib import Path

from .plumbing import load_commit
from .ref import HashRef


class MergeResult(Enum):
    """Enumeration of possible merge outcomes."""

    DISJOINT = auto()       # Case 1: No common ancestor - cannot merge
    UP_TO_DATE = auto()     # Case 2: HEAD is already at or past target
    FAST_FORWARD = auto()   # Case 3: Target is ahead of HEAD - can fast-forward
    THREE_WAY = auto()      # Case 4: 3-way merge


def get_common_ancestor(objects_dir: Path, hash1: str, hash2: str) -> str | None:
    """Find the lowest common ancestor (LCA) of two commits.

    :param objects_dir: Path to the objects directory.
    :param hash1: The hash of the first commit.
    :param hash2: The hash of the second commit.
    :return: The hash of the common ancestor, or None if no common ancestor is found."""
    if hash1 == hash2:
        return hash1

    ancestors1 = _collect_ancestors(objects_dir, hash1)

    # Walk ancestors of hash2 and return the first match
    current = hash2
    while current:
        if current in ancestors1:
            return current
        commit = load_commit(objects_dir, current)
        current = commit.parent

    return None


def _collect_ancestors(objects_dir: Path, commit_hash: str) -> set[str]:
    """Collect all ancestors of a commit including itself.

    :param objects_dir: Path to the objects directory.
    :param commit_hash: The hash of the commit to start from.
    :return: A set of ancestor hashes."""
    ancestors = set()
    current = commit_hash
    while current:
        ancestors.add(current)
        commit = load_commit(objects_dir, current)
        current = commit.parent
    return ancestors
