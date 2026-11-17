# Step 44: pandas

> **Assumes what you already studied:** Series/DataFrame, `read_csv` basics, concatenating rows, `to_string`, `read_json`, `index_col`, filtering, aggregate functions, basic `groupby`, and cleaning with `drop`/`dropna`/`fillna`/`replace`/`rename`/`astype`/`drop_duplicates`. This doc covers only the gaps: label alignment, Copy-on-Write, merges, advanced grouping, dtypes/dates/strings, reshaping/time series, and memory. Verified against pandas 3.1.1, November 2026.

## The Problem

The basics get a CSV into a DataFrame. Real datasets add labeled indexes that misalign, joins that duplicate rows, groupbys you cannot inspect, dtypes that turn numbers into strings, and files that do not fit in RAM. pandas runs all of it without an error.

## Foundational Concepts

- A DataFrame is a labeled 2-D table: a row index, named columns, and one array per column with its own dtype.
- Operations align by **label**, not position. That is the feature and the trap.
- pandas is in-memory. `read_csv` materializes the file in RAM; the file on disk is separate.
- pandas 3.x uses **Copy-on-Write**: chained assignment never updates the original.

## 44.1 Index and alignment (the gap after Series/DataFrame)

- `.loc` = label; `.iloc` = position; `.at`/`.iat` = scalar.
- `.loc` slices include both ends; `.iloc` slices exclude the stop.
- `df[col] = series` aligns by index label. A missing label becomes NaN. Use `.to_numpy()` for positional assignment.
- `set_index` / `reset_index`; duplicate index labels make `.loc` return multiple rows.
- `query`, `isin`, `where`/`mask` for readable filtering.

```python
df = pd.DataFrame({"x": [1, 2, 3]}, index=["a", "b", "c"])
s = pd.Series([10, 20, 30], index=["c", "a", "b"])

df["aligned"] = s             # a=20, b=30, c=10: aligned by label
df["positional"] = s.to_numpy()  # a=10, b=20, c=30: aligned by position
```

## 44.2 read_csv and I/O (the gap after the basics)

- `usecols` to load only needed columns; `dtype` to stop inference surprises; `parse_dates` for dates; `na_values` for custom missing markers.
- `nrows` for a quick peek; `chunksize` for a file too large to load at once.
- `encoding`, `sep`, `on_bad_lines` for messy files.
- `read_json(lines=True)` for JSONL; `orient` must match the writer. `read_parquet` is typed, compressed, and faster than CSV for repeated loads.
- Set dtypes at read time: it is cheaper than converting later and avoids mixed-type columns.

```python
df = pd.read_csv(
    "data.csv",
    usecols=["id", "date", "amount"],
    dtype={"id": "Int64", "amount": "float32"},
    parse_dates=["date"],
    na_values=["", "NA", "unknown"],
)

for chunk in pd.read_csv("huge.csv", chunksize=100_000, dtype={"id": "int64"}):
    ...  # aggregate each chunk; do not append them all to a list
```

## 44.3 Selection and chained assignment (the `.loc`/`.iloc` gap)

- Use `.loc[mask, "col"] = value` for assignment. `df[df.A > 0]["B"] = 0` is chained assignment and does not update `df` under Copy-on-Write (pandas 3.x); it raises a `ChainedAssignmentError` warning.
- `.iloc` does not align; `.loc` does.
- Prefer `.loc` for readability and safety; use `.iloc` when you mean position.
- `where`/`mask` return a same-shape copy; `np.where` returns an array.

```python
df.loc[df["A"] > 0, "B"] = 0          # correct
# df[df["A"] > 0]["B"] = 0            # chained: no effect in pandas 3.x
```

## 44.4 GroupBy: seeing groups and going beyond `.mean()`

- `grouped = df.groupby("A")` is lazy; `print(grouped)` shows an object, not the data.
- `grouped.groups` -> dict `{key: [index labels]}`; `grouped.ngroups`; `grouped.size()`; `grouped.get_group("foo")`; iterate `for name, group in grouped`.
- `agg` accepts a list, dict, or named aggregation; `as_index=False` keeps keys as columns.
- `transform` returns a same-index result (e.g. group mean broadcast); `filter` drops groups; `apply` is flexible but slower.
- `dropna=False` keeps NaN groups; `observed=True` avoids unobserved category combinations.

```python
g = df.groupby("A")
print(g.groups)            # {"bar": [1, 3], "foo": [0, 2, 4]}
print(g.size())            # count per group
print(g.get_group("foo"))  # the actual rows
for name, group in g:
    print(name, group)

df.groupby("A", as_index=False).agg(
    min_b=("B", "min"),
    max_b=("B", "max"),
    n=("B", "size"),
)
```

## 44.5 Merges, joins, and concatenation

- `pd.merge(left, right, how=..., on=...)` is SQL-style. `left_on`/`right_on` for different key names; `left_index`/`right_index` for index keys; `suffixes` for overlapping columns.
- `validate=` (`one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`) catches duplicate keys before they explode the row count.
- `indicator=True` adds `_merge` with `left_only`, `right_only`, `both`.
- Many-to-many duplicate keys produce a Cartesian product. Check `len(left)`, `len(right)`, `len(result)`.
- `pd.concat` for rows/columns; `ignore_index=True`; `keys=` for a MultiIndex; collect frames in a list and concat once.
- `join` is index-based; `merge_asof` matches nearest time keys.

```python
out = pd.merge(
    orders, customers,
    on="customer_id", how="left",
    validate="many_to_one", indicator=True,
)
print(out["_merge"].value_counts())
```

## 44.6 dtypes, missing data, strings, and dates

- `astype` is a general converter, not just 0/1: `"1"` -> `int`, `1` -> `str`, `True` -> `1`, `1/0` -> `bool`, `1.9` -> `1` (truncates). It fails on non-numeric strings and on `NaN` -> `int`.
- Use `pd.to_numeric(s, errors="coerce")` for messy numeric strings; `pd.to_datetime(s, errors="coerce")` for dates; nullable `Int64`/`boolean`/`string` if you need to keep `NA`.
- pandas 3.x uses a `str` dtype for strings by default; `object` still appears for mixed columns. `convert_dtypes()` converts to nullable dtypes.
- `category` for repeated strings: less memory and faster groupby (use `observed=True`).
- Strings: `.str.lower()`, `.str.strip()`, `.str.replace()`, `.str.contains(..., na=False)`, `.str.split()` + `explode()`.
- Missing: `isna`/`notna`, `dropna(subset=..., how=...)`, `fillna`, `ffill`/`bfill`, `interpolate`.
- `pd.NA` comparisons return `NA`, not `False`; use `isna`.

```python
s = pd.Series(["1", "2", "x"])
pd.to_numeric(s, errors="coerce")        # [1.0, 2.0, NaN]
pd.Series([1, None]).astype("Int64")      # [1, <NA>]

df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["name"] = df["name"].str.strip().str.lower()
df["kind"] = df["kind"].astype("category")
```

## 44.7 Reshaping and time series

- `pivot_table` aggregates duplicates; `pivot` errors if duplicates exist.
- `melt` goes wide -> long; `stack`/`unstack` move index levels; `crosstab` counts combinations; `explode` expands list-like cells.
- `resample` needs a datetime index; `rolling`/`expanding` for windows; `shift`/`diff`/`pct_change` for lags and changes.

```python
wide = df.pivot_table(index="id", columns="metric", values="value", aggfunc="sum")
long = wide.reset_index().melt(id_vars="id", var_name="metric", value_name="value")

ts = df.set_index("date").sort_index()
ts["rolling_7"] = ts["value"].rolling(7).mean()
monthly = ts["value"].resample("MS").sum()
```

## 44.8 Memory: where the DataFrame lives and what to do when it does not fit

- `pd.read_csv` builds an in-memory DataFrame. The file stays on disk; the DataFrame is separate. Changes do not write back unless you call `to_csv`.
- Each column is a NumPy/extension array; the index and strings add overhead. Check `df.info(memory_usage="deep")`, `df.memory_usage(deep=True).sum()`, `df.nbytes`.
- Biggest wins: `usecols`, `dtype` (`float32`, `category`), drop unused columns, avoid full copies, and use Parquet/Arrow instead of CSV.
- If it does not fit: `read_csv(chunksize=...)` and aggregate per chunk; `dask`, `polars`, `duckdb`, or a database; a streaming data loader for training.
- `inplace=True` is not a memory strategy and is being discouraged; assign the result instead.

```python
print(df.info(memory_usage="deep"))
print(df.memory_usage(deep=True).sort_values(ascending=False))
```

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Assignment silently does nothing | chained indexing under CoW | `df.loc[mask, "col"] = value` |
| New column is full of NaN | Series assigned by position, not label | `.to_numpy()` or align the index |
| Merge row count explodes | duplicate keys on both sides | `validate=`; check `len` before/after |
| `print(groupby)` shows an object | GroupBy is lazy | `.groups`, `.get_group`, iterate |
| `astype(int)` raises | NaN or non-numeric strings | `pd.to_numeric`, `Int64` |
| Numbers stored as strings | mixed values / bad inference | `dtype=` on read; `convert_dtypes` |
| Memory much larger than CSV | strings/object/index/copies | `category`, `usecols`, `dtype`, Parquet |
| `dropna()` removes too much | default drops any row with an NA | `subset=`, `how="all"` |
| `pd.NA == pd.NA` is not True | NA propagation | `isna()` |
| Dates stay strings | not parsed | `parse_dates` / `to_datetime` |
| `concat` in a loop is slow | repeated copies | collect a list, concat once |
| `apply` is slow | row-wise Python | vectorized ops, `agg`, `transform` |

## Quick Reference

| Need | Use |
|---|---|
| label selection | `df.loc[rows, cols]` |
| positional selection | `df.iloc[rows, cols]` |
| scalar | `df.at[row, col]` / `df.iat[i, j]` |
| mask assignment | `df.loc[mask, "col"] = value` |
| safe numeric parse | `pd.to_numeric(s, errors="coerce")` |
| date parse | `pd.to_datetime(s, errors="coerce")` |
| nullable int | `astype("Int64")` |
| categorical | `astype("category")` |
| group counts | `grouped.size()` |
| one group | `grouped.get_group(key)` |
| group dict | `grouped.groups` |
| named agg | `.agg(name=("col", "func"))` |
| same-index group result | `.transform("mean")` |
| merge validation | `merge(..., validate="many_to_one")` |
| merge audit | `merge(..., indicator=True)` |
| wide -> long | `melt` |
| long -> wide | `pivot_table` |
| memory | `df.memory_usage(deep=True)` |
| chunked read | `pd.read_csv(path, chunksize=...)` |

## Theory Summary

- A DataFrame is a labeled table, not just an array. Labels drive alignment, selection, and joins.
- Copy-on-Write means chained assignment is not a style preference; it is a correctness rule.
- `merge` is a relational operation. Duplicate keys multiply rows; validate before you trust the result.
- A GroupBy object is lazy. Inspect it with `groups`, `get_group`, `size`, or iteration; aggregate/transform to get a DataFrame.
- `astype` converts clean types; `to_numeric`/`to_datetime` parse messy data. Nullable dtypes preserve `NA`.
- pandas is in-memory. For big data, reduce columns/dtypes, chunk, or move to a columnar/out-of-core engine.

## Deliverable

`Phase 2(ML)/STEP 44/step44-pandas/`:
- `audit.py` — load a CSV with an explicit schema, profile missing values/duplicates, standardize column names, parse dates, run a validated merge, summarize a groupby, and print memory usage.
- `test_audit.py` — tests for schema enforcement, duplicate detection, merge `validate`, groupby counts, and dtype conversion.
- `README.md` — commands, expected output, and a note on what each check catches.

**Check:** `python audit.py data.csv` prints row/column counts, missing-value counts, duplicate counts, dtypes, and memory; a bad merge raises `MergeError`; a groupby prints one row per group; `pytest -q` passes.
