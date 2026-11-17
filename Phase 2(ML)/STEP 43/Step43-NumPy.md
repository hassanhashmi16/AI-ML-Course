# Step 43: NumPy

> **Assumes the basics.** This is the trap sheet: the non-obvious parts that cause silent bugs, not an API tour. Verified against NumPy 2.5.4, November 2026.

## The Problem

You can create and slice arrays. The bugs that survive that stage are ownership (a slice mutates the training set), shape (`(N,)` becomes `(N,N)`), precision (float32 accumulation or a naive softmax), and solver (`inv` on a nearly singular matrix). NumPy runs all of them without an error.

## Foundational Concepts

- `ndarray` = data buffer + shape + dtype + strides. A **view** changes metadata; a **copy** changes the buffer.
- Shape is the contract. Broadcasting aligns from the right; `(N,)` and `(N,1)` are different.
- `*` is elementwise; `@` is contraction.
- `solve` beats `inv`; `lstsq` beats the normal equations; `cond` tells you how many digits you can trust.
- float32 is the ML default; float64 is the reference.

## 43.1 Array object

- `np.array` copies; `np.asarray` avoids the copy when the dtype matches.
- `reshape`/`ravel` may be views; `flatten` always copies.
- Strides are in bytes; `a.T.strides` is swapped. `np.shares_memory(a,b)` is the reliable check.
- C order stores the last axis contiguously; Fortran the first. `np.ascontiguousarray` converts.

## 43.2 Broadcasting

- Align right; pad with 1s; each pair must be equal or 1.
- `(N,)` + `(N,1)` → `(N,N)` silently. Use `keepdims=True` on reductions.
- An `(N,M,D)` broadcast can OOM. Use `x2[:,None] + y2[None,:] - 2*(X@Y.T)`, clamp negatives, chunk rows.
- `X[:,None,:] - Y[None,:,:]` is the version that allocates the huge intermediate; don't.

## 43.3 Matrix multiplication

- `A * B` elementwise; `A @ B` contraction.
- `matmul` batches leading axes; `np.dot` does not: 3-D gives `(2,3,2,5)` vs `(2,3,5)`.
- `.T` on >2-D reverses all axes; use `swapaxes(-1,-2)`.
- Linear layer `Y = X @ W.T + b`; attention `Q @ K.swapaxes(-1,-2)`.

## 43.4 linalg

- `solve(A,b)` for square full-rank; `lstsq(A,b)` otherwise; `inv` only when needed.
- Normal equations square `cond`; `lstsq` uses SVD.
- Check `cond`; `eigh` for symmetric; `slogdet` for large determinants.
- `[[1,1],[1,1+1e-8]]` has `cond ~4e8`; a 1e-8 change in `b` moves the answer by ~1.

## 43.5 Vectorization

- Moves the loop into C; does not remove memory traffic.
- Elementwise is bandwidth-bound; matmul is compute-bound.
- Temporaries cost; use `out=`; `np.vectorize` still loops in Python.
- Tiny arrays: measure; a Python loop can win.

## 43.6 Views and copies

- Slice/transpose: view. Fancy/boolean index: copy. `flatten`: copy. `ravel`: view if possible.
- A small slice keeps the whole buffer alive: `big[:10].copy()`.
- `torch.from_numpy` shares CPU memory; `torch.tensor` copies.
- `np.array` copies; `np.asarray` does not if dtype matches.

## 43.7 Axes and indexing

- `axis=0` collapses rows → one value per column; `axis=1` the reverse.
- `keepdims=True` keeps the result broadcastable.
- Masks/fancy indexing copy; `np.add.at` for duplicate indices; `argpartition` for top-k.
- `a[[0,0]] += 1` increments once; `np.add.at(a,[0,0],1)` twice.

## 43.8 Precision

- float32 ~7 digits; float64 ~16.
- Reductions keep the input dtype: `np.sum(x, dtype=np.float64)`.
- Cancellation: `[1e8,1,-1e8]` sums to 0 in float32, 1 in float64.
- Softmax: subtract the max before `exp`; use `log_softmax` for cross-entropy.
- Compare with `np.isclose`, not `==`; `np.var` uses `ddof=0` by default.

## 43.9 RNG

- `rng = np.random.default_rng(seed)`, not `np.random.seed`.
- `SeedSequence(seed).spawn(n)` for independent streams.
- Same seed is not enough: seed Python, NumPy, and the framework; record versions.
- Don't reseed per worker with the same seed.

## 43.10 einsum

- Output indices kept; input-only indices summed; `ii` takes the diagonal.
- Use explicit `->`; `optimize=True` for 3+ operands.
- Attention: `np.einsum("bhtd,bhsd->bhts", Q, K)`.
- For a plain 2-D matmul, `@` is usually faster.

## Pitfalls

| Symptom | Fix |
|---|---|
| model never learns | `*` vs `@` |
| `(N,N)` blowup | `(N,)` vs `(N,1)`; `[:, None]` |
| broadcast error after reduction | `keepdims=True` |
| per-column vs per-row | check axis |
| slice mutates original | `.copy()` |
| fancy-index mutation does nothing | fancy indexing copies |
| memory grows | view retains buffer |
| softmax `nan` | subtract max |
| solve inaccurate | `solve`, not `inv`; check `cond` |
| random split changes | pass a `Generator` |
| batched matmul shape | `swapaxes(-1,-2)` |

## Quick Reference

| Need | Use |
|---|---|
| no-copy conversion | `np.asarray(x)` |
| ownership | `np.array(x)` / `x.copy()` |
| alias check | `np.shares_memory(a,b)` |
| batched transpose | `a.swapaxes(-1,-2)` |
| solve | `np.linalg.solve(A,b)` |
| least squares | `np.linalg.lstsq(A,b,rcond=None)` |
| conditioning | `np.linalg.cond(A)` |
| symmetric eig | `np.linalg.eigh(A)` |
| safe determinant | `np.linalg.slogdet(A)` |
| top-k | `np.argpartition(a,-k)[-k:]` |
| per-row select | `np.take_along_axis(a,idx,axis=1)` |
| repeated-index add | `np.add.at(a,idx,vals)` |
| private RNG | `np.random.default_rng(seed)` |
| independent streams | `SeedSequence(seed).spawn(n)` |

## Theory Summary

- Buffer + metadata; views vs copies.
- Shape is the contract; broadcasting is a rule.
- `*` vs `@`; `matmul` vs `dot`.
- `solve`/`lstsq`/`cond`; `eigh`; `slogdet`.
- Vectorization moves the loop, not the memory.
- float32 vs float64; stable softmax.
- RNG state; `einsum` notation.

## Deliverable

`Phase 2(ML)/STEP 43/step43-numpy/`: `numpy_lab.py` (`views`, `broadcast`, `linalg`, `bench`), `test_numpy_lab.py`, `README.md`. Check: view vs copy, chunked distances match brute force, `lstsq` recovers `[2,-3]`, float64 Hilbert error << float32, `pytest -q`.
