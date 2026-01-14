"""Tests for merge functionality."""

from pathlib import Path

from libcaf.merge import MergeResult, merge
from libcaf.ref import HashRef
from libcaf.repository import Repository


def test_merge_disjoint_returns_disjoint_and_head_unchanged(temp_repo: Repository) -> None:
    """Case 1: Disjoint branches with no common ancestor should return DISJOINT.

    The merge should not modify HEAD when branches are disjoint.
    """
    # Create first commit on main branch
    (temp_repo.working_dir / "a.txt").write_text("a")
    commit_a = temp_repo.commit_working_dir("Author", "Commit A")

    # Create an isolated branch with no common ancestor
    # Switch to a new branch that starts fresh (no parent)
    (temp_repo.repo_path() / "HEAD").write_text("ref: heads/isolated\n")
    isolated_ref: Path = temp_repo.refs_dir() / "heads" / "isolated"
    isolated_ref.parent.mkdir(parents=True, exist_ok=True)
    isolated_ref.write_text("")

    (temp_repo.working_dir / "b.txt").write_text("b")
    commit_b = temp_repo.commit_working_dir("Author", "Commit B")

    # Record HEAD before merge attempt
    head_before = temp_repo.head_commit()

    # Attempt to merge disjoint branches
    result = merge(temp_repo, HashRef(commit_a))

    # Should return DISJOINT enum (not raise exception)
    assert result == MergeResult.DISJOINT

    # HEAD should remain unchanged
    assert temp_repo.head_commit() == head_before


def test_merge_up_to_date_returns_up_to_date(temp_repo: Repository) -> None:
    """Case 2: Merging an ancestor commit should return UP_TO_DATE.

    When HEAD is already at or past the target, nothing should change.
    """
    (temp_repo.working_dir / "file.txt").write_text("v1")
    root = temp_repo.commit_working_dir("Author", "Root commit")

    (temp_repo.working_dir / "file.txt").write_text("v2")
    child = temp_repo.commit_working_dir("Author", "Child commit")

    # HEAD is now at child, trying to merge root (an ancestor)
    head_before = temp_repo.head_commit()

    result = merge(temp_repo, HashRef(root))

    assert result == MergeResult.UP_TO_DATE
    assert temp_repo.head_commit() == head_before
    assert temp_repo.head_commit() == child


def test_merge_fast_forward_moves_head(temp_repo: Repository) -> None:
    """Case 3: Fast-forward merge should move HEAD to target.

    When target is ahead of HEAD with a linear history, HEAD should advance.
    """
    (temp_repo.working_dir / "file.txt").write_text("v1")
    root = temp_repo.commit_working_dir("Author", "Root commit")

    (temp_repo.working_dir / "file.txt").write_text("v2")
    child = temp_repo.commit_working_dir("Author", "Child commit")

    # Move HEAD back to root (simulating being behind)
    temp_repo.update_head(HashRef(root))
    assert temp_repo.head_commit() == root

    # Merge child into current HEAD (root)
    result = merge(temp_repo, HashRef(child))

    assert result == MergeResult.FAST_FORWARD
    assert temp_repo.head_commit() == child


def test_merge_three_way_returns_three_way(temp_repo: Repository) -> None:
    """Case 4: Diverged branches should return THREE_WAY.

    When both branches have commits after the common ancestor,
    a 3-way merge is required. For now, this is not fully implemented
    but should be classified correctly.
    """
    (temp_repo.working_dir / "file.txt").write_text("base")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Create commit on left branch
    (temp_repo.working_dir / "file.txt").write_text("left change")
    left = temp_repo.commit_working_dir("Author", "Left commit")

    # Go back to base and create commit on right branch
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("right change")
    right = temp_repo.commit_working_dir("Author", "Right commit")

    # Now HEAD is at right, try to merge left
    # Both left and right have diverged from base
    head_before = temp_repo.head_commit()

    # Since 3-way merge is not implemented, we expect the merge to classify
    # this as THREE_WAY. The actual merge behavior will be added later.
    # For now, test that the classification is correct by checking the result.
    result = merge(temp_repo, HashRef(left))

    assert result == MergeResult.THREE_WAY
    # HEAD should remain unchanged since merge wasn't actually performed
    assert temp_repo.head_commit() == head_before
