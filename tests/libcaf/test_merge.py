"""Tests for merge functionality."""

import time
import pytest

from libcaf import Commit
from libcaf.merge import MergeResult, get_common_ancestor, MergeConflictError
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


def test_merge_three_way_new_and_change(temp_repo: Repository) -> None:
    """Three-way merge creates a merge commit and updates working dir."""
    (temp_repo.working_dir / "file.txt").write_text("base")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Left changes file.txt
    (temp_repo.working_dir / "file.txt").write_text("left change")
    left = temp_repo.commit_working_dir("Author", "Left commit")

    # Right (branch from base): keeps file.txt as base and adds other.txt
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("base")
    (temp_repo.working_dir / "other.txt").write_text("right change")
    right = temp_repo.commit_working_dir("Author", "Right commit")

    head_before = temp_repo.head_commit()
    result = temp_repo.merge(HashRef(left))

    # HEAD should point to a new merge commit
    assert result == MergeResult.THREE_WAY
    assert temp_repo.head_commit() != head_before
    assert temp_repo.head_commit() != left

    # Working directory should reflect merged result (like checkout)
    assert (temp_repo.working_dir / "file.txt").read_text() == "left change"
    assert (temp_repo.working_dir / "other.txt").read_text() == "right change"


def test_three_way_merge_same_change(temp_repo: Repository) -> None:
    """
    Base: empty
    Left: adds file.txt ("same")
    Right: adds file.txt ("same")
    Merge should succeed (no conflict) and create a merge commit.
    """
    base = temp_repo.commit_working_dir("Author", "Base commit (empty)")

    (temp_repo.working_dir / "file.txt").write_text("same")
    left = temp_repo.commit_working_dir("Author", "Left adds file")

    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("same")
    right = temp_repo.commit_working_dir("Author", "Right adds file")

    head_before = temp_repo.head_commit()  # right
    result = temp_repo.merge(HashRef(left))

    assert result == MergeResult.THREE_WAY
    assert temp_repo.head_commit() != head_before
    assert temp_repo.head_commit() != left

    # Working dir should be updated
    assert (temp_repo.working_dir / "file.txt").read_text() == "same"


def test_three_way_merge_delete_vs_unchanged(temp_repo: Repository) -> None:
    """
    Base: file.txt exists
    Left: deletes file.txt
    Right: leaves file.txt unchanged
    Expected: merge succeeds, file.txt deleted.
    (This matches common Git behavior.)
    """
    (temp_repo.working_dir / "file.txt").write_text("base")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Left deletes
    (temp_repo.working_dir / "file.txt").unlink()
    left = temp_repo.commit_working_dir("Author", "Left deletes file")

    # Right unchanged (branch from base)
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("base")
    right = temp_repo.commit_working_dir("Author", "Right unchanged")

    head_before = temp_repo.head_commit()  # right
    result = temp_repo.merge(HashRef(left))

    assert result == MergeResult.THREE_WAY
    assert temp_repo.head_commit() != head_before
    assert not (temp_repo.working_dir / "file.txt").exists()


def test_three_way_merge_delete_vs_modified_is_conflict(temp_repo: Repository) -> None:
    """
    Base: file.txt exists
    Left: deletes file.txt
    Right: modifies file.txt
    Expected: conflict.
    """
    (temp_repo.working_dir / "file.txt").write_text("base")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Left deletes
    (temp_repo.working_dir / "file.txt").unlink()
    left = temp_repo.commit_working_dir("Author", "Left deletes file")

    # Right modifies (branch from base)
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("right change")
    right = temp_repo.commit_working_dir("Author", "Right modifies file")

    head_before = temp_repo.head_commit()  # right
    with pytest.raises(MergeConflictError):
        temp_repo.merge(HashRef(left))

    # HEAD must remain unchanged after failed merge
    assert temp_repo.head_commit() == head_before


def test_three_way_merge_same_file_modified_auto_merge_success(temp_repo: Repository) -> None:
    """
    Base: multi-line file
    Left: changes line 1
    Right: changes line 3
    Expected: auto-merge succeeds (no conflict) and result contains both edits.
    """
    base_text = "line1\nline2\nline3\n"
    (temp_repo.working_dir / "file.txt").write_text(base_text)
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Left changes line1
    (temp_repo.working_dir / "file.txt").write_text("LEFT1\nline2\nline3\n")
    left = temp_repo.commit_working_dir("Author", "Left changes line1")

    # Right changes line3 (branch from base)
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("line1\nline2\nRIGHT3\n")
    right = temp_repo.commit_working_dir("Author", "Right changes line3")

    head_before = temp_repo.head_commit()  # right
    result = temp_repo.merge(HashRef(left))

    assert result == MergeResult.THREE_WAY
    assert temp_repo.head_commit() != head_before

    # Working dir should contain both changes
    merged_text = (temp_repo.working_dir / "file.txt").read_text()
    assert merged_text == "LEFT1\nline2\nRIGHT3\n"


def test_three_way_merge_same_file_modified_overlap_conflict(temp_repo: Repository) -> None:
    """
    Base: multi-line file
    Left: changes line2 -> LEFT2
    Right: changes line2 -> RIGHT2
    Expected: conflict (overlapping changes).
    """
    (temp_repo.working_dir / "file.txt").write_text("line1\nline2\nline3\n")
    base = temp_repo.commit_working_dir("Author", "Base commit")

    # Left changes line2
    (temp_repo.working_dir / "file.txt").write_text("line1\nLEFT2\nline3\n")
    left = temp_repo.commit_working_dir("Author", "Left changes line2")

    # Right changes line2 differently (branch from base)
    temp_repo.update_head(HashRef(base))
    (temp_repo.working_dir / "file.txt").write_text("line1\nRIGHT2\nline3\n")
    right = temp_repo.commit_working_dir("Author", "Right changes line2")

    head_before = temp_repo.head_commit()  # right
    with pytest.raises(MergeConflictError):
        temp_repo.merge(HashRef(left))

    assert temp_repo.head_commit() == head_before