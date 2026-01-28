"""Merge functionality for libcaf."""

from enum import Enum, auto

from .ref import HashRef
from pathlib import Path

from . import Tree, TreeRecord, TreeRecordType
from .plumbing import (
    hash_object,
    load_commit,
    load_tree,
    save_tree,
    open_content_for_reading,
)
from .repository import Repository
from typing import Dict, Optional

from three_merge import merge as three_merge_merge

class MergeResult(Enum):
    """Enumeration of possible merge outcomes."""

    DISJOINT = auto()       # Case 1: No common ancestor - cannot merge
    UP_TO_DATE = auto()     # Case 2: HEAD is already at or past target
    FAST_FORWARD = auto()   # Case 3: Target is ahead of HEAD - can fast-forward
    THREE_WAY = auto()      # Case 4: 3-way merge


def get_common_ancestor(objects_dir: Path, hash1: str, hash2: str) -> str | None:
    """Find the lowest common ancestor (LCA) of two commits.

    :param objects_dir: Path to the object's directory.
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
    """Collect all ancestors of a commit including itrepo.

    :param objects_dir: Path to the object's directory.
    :param commit_hash: The hash of the commit to start from.
    :return: A set of ancestor hashes."""
    ancestors = set()
    current = commit_hash
    while current:
        ancestors.add(current)
        commit = load_commit(objects_dir, current)
        current = commit.parent
    return ancestors


class MergeConflictError(Exception):
    """Exception raised for merge conflicts."""



def merge_trees(repo: Repository, base_h: str, target_h: str, source_h: str) -> str:
    """Merge three trees and return the hash of the merged tree.

    :param repo: The repository.
    :param base_h: The hash of the base tree.
    :param target_h: The hash of the target tree.
    :param source_h: The hash of the source tree.
    :return: The hash of the merged tree.
    """
    objects_dir = repo.objects_dir()

    base_t = load_tree(objects_dir, base_h)
    target_t = load_tree(objects_dir, target_h)
    source_t = load_tree(objects_dir, source_h)

    base_records = base_t.records if base_t else {}
    target_records = target_t.records if target_t else {}
    source_records = source_t.records if source_t else {}

    merged_records: dict[str, TreeRecord] = {}
    records = set(base_records.keys()) | set(target_records.keys()) | set(source_records.keys())

    for record in records:
        base_record = base_records.get(record)
        target_record = target_records.get(record)
        source_record = source_records.get(record)

        # Base is None (new file/dir)
        if base_record is None:
            # added in target and source
            if target_record is not None and source_record is not None:
                if target_record == source_record:
                    merged_records[record] = target_record
                    continue
                else:
                    raise MergeConflictError(f"conflict: added different files: {record}")

            # added in target only
            if target_record is not None:
                merged_records[record] = target_record
                continue

            # added in source only
            if source_record is not None:
                merged_records[record] = source_record
                continue

            # all there None
            continue

        # Base is not None
        else:
            # deleted in both
            if target_record is None and source_record is None:
                continue

            # deleted in one, unchanged in the other
            if (target_record is None and source_record == base_record) or (
                    source_record is None and target_record == base_record):
                continue

            # deleted in one, changed in the other
            if (target_record is None and source_record != base_record) or (
                    source_record is None and target_record != base_record):
                raise MergeConflictError(f"conflict: one deleted and one changed: {record}")

            # all three not None:

            # same file
            if source_record == target_record:
                merged_records[record] = source_record
                continue

            # target is different
            if source_record == base_record:
                merged_records[record] = target_record
                continue

            # source is different
            if target_record == base_record:
                merged_records[record] = source_record
                continue

            # both changed:

            # records are trees => merge recursively
            if (base_record.type == TreeRecordType.TREE and
                    target_record.type == TreeRecordType.TREE and
                    source_record.type == TreeRecordType.TREE):
                merged_subtree = merge_trees(repo, base_record.hash, target_record.hash, source_record.hash)
                merged_records[record] = TreeRecord(TreeRecordType.TREE, merged_subtree, record)
                continue

            # records are blobs => try auto-merge using three_merge
            if (base_record.type == TreeRecordType.BLOB
                    and target_record.type == TreeRecordType.BLOB
                    and source_record.type == TreeRecordType.BLOB):
                try:
                    base_text = _read_blob_text(objects_dir, base_record.hash)
                    target_text = _read_blob_text(objects_dir, target_record.hash)
                    source_text = _read_blob_text(objects_dir, source_record.hash)
                except Exception as e:
                    raise MergeConflictError(f"could not decode as UTF-8 for auto-merge file: {record}") from e

                merged_text = three_merge_merge(source_text, target_text, base_text)

                # result contains conflict markers => raise conflict
                if ("<<<<<<<" in merged_text) and ("=======" in merged_text) and (">>>>>>>" in merged_text):
                    raise MergeConflictError(f"conflict in file: {record}")

                # auto-merge succeeded => save merged content as a new blob and store its hash
                merged_blob_hash = _save_blob_text(repo, merged_text)
                merged_records[record] = TreeRecord(TreeRecordType.BLOB, merged_blob_hash, record)
                continue

            # different types of records
            raise MergeConflictError(f"different types of files: {record}")
    
    merged_tree = Tree(merged_records)
    save_tree(objects_dir, merged_tree)
    return hash_object(merged_tree)


# Helpers -------------------------------------------------------------------------------------------

def _read_blob_text(objects_dir: Path, blob_hash: str) -> str:
    """Read a blob's content from the object store and decode it as UTF-8.

    Raises UnicodeDecodeError if the blob isn't valid UTF-8.
    """
    with open_content_for_reading(objects_dir, blob_hash) as f:
        data = f.read()
    return data.decode("utf-8")


def _save_blob_text(repo: Repository, text: str) -> str:
    """Save text as a blob in the object store and return its hash (OID)."""
    import tempfile

    data = text.encode("utf-8")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        blob = repo.save_file_content(tmp_path)      # writes blob object to store
        blob_hash = hash_object(blob)                # returns HashRef (subclass of str)
        return str(blob_hash)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
