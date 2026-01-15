"""Tests for merge functionality."""

import time

from libcaf import Commit
from libcaf.merge import MergeResult, get_common_ancestor
from libcaf.plumbing import hash_object, load_commit, save_commit
from libcaf.ref import HashRef
from libcaf.repository import Repository


def test_merge_disjoint(temp_repo: Repository) -> None:
    """Disjoint branches return DISJOINT and HEAD unchanged."""
    (temp_repo.working_dir / "a.txt").write_text("a")
    temp_repo.commit_working_dir("Author", "Commit A")

    # Create a disconnected commit with no common ancestor
    commit = Commit("tree_hash", "Author", "Disconnected", int(time.time()), None)
    save_commit(temp_repo.objects_dir(), commit)

    head_before = temp_repo.head_commit()
    result = temp_repo.merge(HashRef(hash_object(commit)))

    assert result == MergeResult.DISJOINT
    assert temp_repo.head_commit() == head_before


def test_merge_up_to_date(temp_repo: Repository) -> None:
    """Merging an ancestor returns UP_TO_DATE and HEAD unchanged."""
    (temp_repo.working_dir / "file.txt").write_text("v1")
    root = temp_repo.commit_working_dir("Author", "Root commit")

    (temp_repo.working_dir / "file.txt").write_text("v2")
    child = temp_repo.commit_working_dir("Author", "Child commit")

    head_before = temp_repo.head_commit()
    result = temp_repo.merge(HashRef(root))

    assert result == MergeResult.UP_TO_DATE
    assert temp_repo.head_commit() == head_before


def test_merge_fast_forward(temp_repo: Repository) -> None:
    """Fast-forward moves HEAD to target."""
    (temp_repo.working_dir / "file.txt").write_text("v1")
    root = temp_repo.commit_working_dir("Author", "Root commit")

    (temp_repo.working_dir / "file.txt").write_text("v2")
    child = temp_repo.commit_working_dir("Author", "Child commit")

    temp_repo.update_head(HashRef(root))
    result = temp_repo.merge(HashRef(child))

    assert result == MergeResult.FAST_FORWARD
    assert temp_repo.head_commit() == child


def test_merge_three_way(temp_repo: Repository) -> None:
    """Three-way merge creates a merge commit."""
    (temp_repo.working_dir / "file.txt").write_text("base")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    (temp_repo.working_dir / "file.txt").write_text("left change")
    left = temp_repo.commit_working_dir("Author", "Left commit")

    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("right change")
    right = temp_repo.commit_working_dir("Author", "Right commit")

    head_before = temp_repo.head_commit()
    result = temp_repo.merge(HashRef(left))

    # HEAD should point to a new merge commit
    assert result == MergeResult.THREE_WAY
    assert temp_repo.head_commit() != head_before
    assert temp_repo.head_commit() != left
