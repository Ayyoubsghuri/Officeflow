"""Pure DataFrame transformations (no file access, no GUI)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

import pandas as pd

from officeflow.core.operation import OperationError
from officeflow.services.textnorm import header_key, normalize_text, strip_invisible


# -- columns -------------------------------------------------------------
@dataclass
class ColumnMatch:
    source: str
    original: str
    canonical: str
    kind: str  # 'exact' | 'similar' | 'fuzzy' | 'new'


def resolve_columns(frame: pd.DataFrame, names: Sequence[str]) -> list[str]:
    """Map user-typed column names to real ones, forgiving case, spacing,
    accents and Arabic letter variants."""
    by_key = {header_key(c): c for c in reversed(list(frame.columns))}
    resolved: list[str] = []
    for name in names:
        if name in frame.columns:
            resolved.append(name)
        elif header_key(name) in by_key:
            resolved.append(by_key[header_key(name)])
        else:
            available = ", ".join(map(str, frame.columns))
            raise OperationError(f"Column “{name}” not found. Available columns: {available}.")
    return resolved


def _digits(key: str) -> str:
    return "".join(c for c in key if c.isdigit())


def unify_columns(
    frames: Sequence[tuple[str, pd.DataFrame]], mode: str = "fuzzy", threshold: float = 0.85
) -> tuple[list[pd.DataFrame], list[ColumnMatch]]:
    """Rename the columns of every frame to a shared set of names.

    The first frame defines the reference names. ``mode``: ``exact`` (names
    must be identical), ``similar`` (ignore case, spaces, punctuation and
    accents) or ``fuzzy`` (also accept small spelling differences). Columns
    whose numbers differ (``Prix 2023`` / ``Prix 2024``) are never merged.
    """
    canonical: list[str] = []
    keys: list[str] = []
    matches: list[ColumnMatch] = []
    renamed: list[pd.DataFrame] = []
    for label, frame in frames:
        used: set[int] = set()
        mapping: dict[str, str] = {}
        for column in frame.columns:
            key = header_key(column)
            target, kind = None, "new"
            for index, name in enumerate(canonical):
                if index not in used and name == column:
                    target, kind = index, "exact"
                    break
            if target is None and mode != "exact" and key:
                for index, other in enumerate(keys):
                    if index not in used and other == key:
                        target, kind = index, "similar"
                        break
            if target is None and mode == "fuzzy" and len(key) >= 4:
                best = 0.0
                for index, other in enumerate(keys):
                    if index in used or _digits(other) != _digits(key):
                        continue
                    score = SequenceMatcher(None, key, other).ratio()
                    if score >= threshold and score > best:
                        target, kind, best = index, "fuzzy", score
            if target is None:
                canonical.append(str(column))
                keys.append(key)
                target = len(canonical) - 1
            used.add(target)
            mapping[column] = canonical[target]
            matches.append(ColumnMatch(label, str(column), canonical[target], kind))
        renamed.append(frame.rename(columns=mapping))
    return renamed, matches


def merge_frames(
    frames: Sequence[tuple[str, pd.DataFrame]], mode: str = "fuzzy", source_column: str = ""
) -> tuple[pd.DataFrame, list[ColumnMatch]]:
    renamed, matches = unify_columns(frames, mode)
    parts = []
    for (label, _), frame in zip(frames, renamed):
        if source_column:
            frame = frame.copy()
            frame.insert(0, source_column, label)
        parts.append(frame)
    parts = [p for p in parts if not p.empty] or parts[:1]
    return pd.concat(parts, ignore_index=True, sort=False), matches


# -- rows ----------------------------------------------------------------
def _comparable(series: pd.Series) -> pd.Series:
    return series.map(
        lambda v: v if pd.isna(v) else re.sub(r"\s+", " ", normalize_text(str(v))).strip().casefold()
    )


def remove_duplicates(
    frame: pd.DataFrame, subset: Sequence[str] = (), keep: str = "first", loose: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (kept rows, removed rows). ``loose`` ignores case, extra spaces
    and Arabic/Western digit differences when comparing."""
    columns = list(subset) or list(frame.columns)
    probe = frame[columns]
    if loose:
        probe = probe.apply(_comparable)
    duplicated = probe.duplicated(keep=keep if keep in ("first", "last") else False)
    return frame[~duplicated].reset_index(drop=True), frame[duplicated].reset_index(drop=True)


@dataclass
class CleanOptions:
    trim: bool = True
    collapse_spaces: bool = True
    remove_invisible: bool = True
    western_digits: bool = False
    drop_empty_rows: bool = True
    drop_empty_columns: bool = False
    text_case: str = "keep"  # keep | upper | lower | title


def clean_frame(frame: pd.DataFrame, options: CleanOptions) -> tuple[pd.DataFrame, dict[str, int]]:
    changed = 0

    def fix(value: object) -> object:
        nonlocal changed
        if not isinstance(value, str):
            return value
        text = value
        if options.remove_invisible:
            text = strip_invisible(text).replace(" ", " ")
        if options.western_digits:
            text = normalize_text(text)
        if options.collapse_spaces:
            text = re.sub(r"[ \t]+", " ", text)
        if options.trim:
            text = text.strip()
        if options.text_case != "keep":
            text = getattr(text, options.text_case)()
        if text != value:
            changed += 1
        return text if text != "" else None

    cleaned = frame.copy()
    for column in cleaned.columns:
        if cleaned[column].dtype == object or pd.api.types.is_string_dtype(cleaned[column]):
            cleaned[column] = cleaned[column].map(fix).astype(object)
    cleaned.columns = [re.sub(r"\s+", " ", strip_invisible(str(c))).strip() for c in cleaned.columns]
    rows_before, columns_before = cleaned.shape
    if options.drop_empty_rows:
        cleaned = cleaned.dropna(how="all")
    if options.drop_empty_columns:
        cleaned = cleaned.dropna(axis=1, how="all")
    stats = {
        "cells_changed": changed,
        "rows_removed": rows_before - len(cleaned),
        "columns_removed": columns_before - cleaned.shape[1],
    }
    return cleaned.reset_index(drop=True), stats


def split_frame(frame: pd.DataFrame, column: str) -> dict[str, pd.DataFrame]:
    """One frame per distinct value, in order of first appearance."""
    labels = frame[column].map(lambda v: "(blank)" if pd.isna(v) or str(v).strip() == "" else str(v).strip())
    return {
        str(value): part.reset_index(drop=True)
        for value, part in frame.groupby(labels, sort=False, dropna=False)
    }


def build_pattern(find: str, regex: bool, case_sensitive: bool) -> re.Pattern[str]:
    if not find:
        raise OperationError("The text to find is empty.")
    try:
        return re.compile(find if regex else re.escape(find), 0 if case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise OperationError(f"Invalid regular expression “{find}”: {exc}") from None


def filter_rows(frame: pd.DataFrame, column: str, mode: str, value: str,
                case_sensitive: bool = False) -> pd.DataFrame:
    """Keep rows whose ``column`` matches. Modes: contains, equals, regex,
    not_empty, empty. Comparison treats Arabic and Western digits alike."""
    series = frame[column]
    if mode == "not_empty":
        return frame[series.notna() & (series.astype(str).str.strip() != "")]
    if mode == "empty":
        return frame[series.isna() | (series.astype(str).str.strip() == "")]
    pattern = build_pattern(normalize_text(value), mode == "regex", case_sensitive)
    test = pattern.fullmatch if mode == "equals" else pattern.search

    def hit(cell: object) -> bool:
        return not pd.isna(cell) and bool(test(normalize_text(str(cell)).strip()))

    return frame[series.map(hit).astype(bool)]


# -- comparison ----------------------------------------------------------
def _same(a: object, b: object) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    if a == b:
        return True
    try:
        return float(a) == float(b)  # 12 (Excel) equals "12.0" (CSV)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def compare_frames(
    first: pd.DataFrame, second: pd.DataFrame, keys: Sequence[str] = ()
) -> dict[str, pd.DataFrame]:
    """Compare two tables. With ``keys`` rows are paired by key value,
    otherwise by position. Returns sheets: only-in-first, only-in-second and
    one line per changed cell."""
    (first, second), _ = unify_columns([("A", first), ("B", second)], "similar")
    shared = [c for c in first.columns if c in second.columns]
    if keys:
        key_columns = resolve_columns(first, keys)
        missing = [k for k in key_columns if k not in second.columns]
        if missing:
            raise OperationError(f"Key column(s) missing in the second file: {', '.join(missing)}.")

        def index_of(frame: pd.DataFrame) -> pd.Series:
            return frame[key_columns].apply(_comparable).astype(str).agg(" | ".join, axis=1)

        a = first.assign(_key=index_of(first)).drop_duplicates("_key").set_index("_key")
        b = second.assign(_key=index_of(second)).drop_duplicates("_key").set_index("_key")
    else:
        key_columns = []
        a, b = first.reset_index(drop=True), second.reset_index(drop=True)
    common = [k for k in a.index if k in b.index]
    changes: list[dict[str, object]] = []
    value_columns = [c for c in shared if c not in key_columns]
    for key in common:
        row_a, row_b = a.loc[key], b.loc[key]
        for column in value_columns:
            if not _same(row_a[column], row_b[column]):
                label = key if key_columns else f"Row {int(key) + 2}"
                changes.append({"Key": label, "Column": column,
                                "First file": row_a[column], "Second file": row_b[column]})
    return {
        "Only in first": a.loc[[k for k in a.index if k not in b.index]].reset_index(drop=True),
        "Only in second": b.loc[[k for k in b.index if k not in a.index]].reset_index(drop=True),
        "Changed cells": pd.DataFrame(changes, columns=["Key", "Column", "First file", "Second file"]),
    }
