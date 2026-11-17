# Step 45: Matplotlib & EDA

> **Assumes what you already studied:** `pyplot`, markers, labels, grids, bar/pie/scatter/histogram plots, subplots, and passing NumPy/pandas data to Matplotlib. This doc covers the gaps: the `fig, ax` API, layout and saving, the EDA workflow, statistical plots, time/categorical/image axes, and the traps that make a chart misleading. Verified against Matplotlib 3.11.2 and pandas 3.1.1, November 2026.

## The Problem

A chart can render and still lie. A truncated y-axis exaggerates a difference, a pie chart with twelve slices hides the ranking, a histogram with five bins invents a shape, and a correlation heatmap without a fixed scale makes weak relationships look strong. The basics teach syntax; EDA is about choosing the right plot and reading it honestly.

## Foundational Concepts

- **Figure** = the whole canvas. **Axes** = one plot area. **Axis** = the ticks and scale inside an Axes.
- `fig, ax = plt.subplots()` is the object-oriented API. `plt.plot()` is the implicit, stateful API. Use `fig, ax` in functions, scripts, and anything reusable.
- A plot is an argument: title, axis labels with units, legend, scale, sample size. If a reader cannot tell what is plotted, the chart is not finished.
- EDA order: shape/dtypes → missingness → univariate distributions → relationships → outliers → label balance → time/group structure.

## 45.1 The `fig, ax` API (the gap after pyplot)

- `fig` owns the canvas; `ax` owns the data. Most methods live on `ax`, not `plt`.
- `plt.subplots()` is the standard constructor. `layout="constrained"` prevents clipped labels and colorbars.
- Use `ax.set_*` for labels, title, limits, and scale; `ax.legend()` for labels; `ax.grid(alpha=0.3)` with `ax.set_axisbelow(True)`.
- `ax.twinx()` adds a secondary y-axis; `ax.secondary_xaxis("top", functions=(...))` adds a converted unit axis.
- For a reusable function, accept `ax` as an argument and draw on it; never call `plt.show()` inside it.

```python
fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
ax.plot(x, y, label="model")
ax.set_xlabel("time [s]")
ax.set_ylabel("error [%]")
ax.set_title("Validation error")
ax.grid(alpha=0.3)
ax.set_axisbelow(True)
ax.legend()
```

## 45.2 Chart choice: what the plot must show

| Question | Plot |
|---|---|
| Distribution of one numeric variable | histogram, KDE, ECDF |
| Distribution by category | box plot, violin plot |
| Relationship between two numerics | scatter, hexbin, 2D histogram |
| Compare categories | bar chart, sorted, zero baseline |
| Part-to-whole, few categories | bar chart (pie only for 2–4 clear slices) |
| Matrix / correlation | heatmap with a fixed scale |
| Image or 2D field | `imshow`, `pcolormesh`, `contourf` |
| Change over time | line chart |
| Label balance | `value_counts` bar chart |

`plot()` is for ordered x-values. A line through unordered categories implies a trend that does not exist. A pie chart with many slices is a bar chart with extra steps.

## 45.3 Subplots and layout

- `fig, axs = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True, layout="constrained")`.
- `axs` is a 2-D array; use `axs.flat` or `axs.ravel()` to loop, or `axs[i, j]` for one panel.
- `sharex`/`sharey` make comparisons honest; label only the outer axes to avoid repetition.
- `subplot_mosaic` handles non-uniform layouts (one tall panel beside two stacked panels).
- `fig.suptitle("...")` for the whole figure; `fig.supxlabel` / `fig.supylabel` for shared labels.
- Put the colorbar on the figure: `fig.colorbar(im, ax=ax)`.

```python
fig, axs = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True, layout="constrained")
for ax, name in zip(axs.flat, ["A", "B", "C", "D"]):
    ax.plot(x, y[name])
    ax.set_title(name)
fig.suptitle("Four diagnostics")

fig, axd = plt.subplot_mosaic([["left", "right"], ["left", "bottom"]], layout="constrained")
```

## 45.4 EDA workflow

1. **Shape and dtypes.** `df.info()`, `df.shape`, `df.dtypes`. A numeric column stored as `str` breaks every later plot.
2. **Missingness.** `df.isna().mean().sort_values(ascending=False)`. Plot it; a 40% missing column is a decision, not a detail.
3. **Univariate.** Histogram/KDE/box for each numeric; `value_counts` bar for each categorical. Look for skew, spikes, impossible values, constant columns.
4. **Outliers.** Box plot or IQR rule; z-scores for roughly normal data. Investigate before deleting; an outlier is often a data-entry error or the most important customer.
5. **Relationships.** Scatter numeric vs numeric; box/violin numeric by category; correlation heatmap; scatter matrix for a small feature set.
6. **Label balance.** `value_counts(normalize=True)`. A 98/2 split makes accuracy meaningless; the bar chart is the first warning.
7. **Time/group structure.** Line plots by group, `resample`, rolling means. Check trend, seasonality, and distribution shift between train and test.

```python
df.info()
print(df.isna().mean().sort_values(ascending=False).head(10))
df.hist(figsize=(10, 6), bins="auto")
print(df[target].value_counts(normalize=True))
```

EDA is not "make every plot". Each plot should answer a question that changes a decision: drop a column, fix a dtype, investigate an outlier, or choose a metric.

## 45.5 Saving and the figure lifecycle

- Save the **figure object**, not the current figure: `fig.savefig(...)`. `plt.savefig` saves whatever is current, which is easy to get wrong after multiple figures.
- Call `savefig` before `plt.show()`. In scripts, `show()` can block; on a headless server, use `matplotlib.use("Agg")`.
- Close figures in loops: `plt.close(fig)`. Otherwise memory grows with every iteration.
- PNG for screenshots and notebooks, SVG/PDF for reports and papers (vector), JPEG for photos. `dpi=150` for web, `dpi=300` for print.
- `bbox_inches="tight"` trims whitespace but can clip annotations; check the output.

```python
import matplotlib
matplotlib.use("Agg")          # headless: CI, servers, scripts
fig.savefig("reports/eda.png", dpi=150, bbox_inches="tight")
plt.close(fig)
```

## 45.6 Statistical plots for EDA

- **Box plot:** median, quartiles, 1.5×IQR whiskers, outliers. Good for comparing distributions by category.
- **Violin plot:** the full shape, not just summary statistics. Use it when the distribution is multimodal.
- **ECDF:** sorted values vs cumulative fraction. Often clearer than a histogram for comparing distributions.
- **Correlation heatmap:** `df.corr(numeric_only=True)`, fixed `vmin=-1, vmax=1`, diverging `RdBu_r`; label the ticks.
- **Scatter matrix:** `pd.plotting.scatter_matrix(df, diagonal="kde")` for a small number of features.
- **2D density:** `hexbin` or `hist2d` when a scatter is overplotted.

```python
fig, ax = plt.subplots(layout="constrained")
ax.boxplot(data, tick_labels=["A", "B", "C"])
ax.set_ylabel("value")

corr = df.corr(numeric_only=True)
fig, ax = plt.subplots(layout="constrained")
im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
fig.colorbar(im, ax=ax)
ax.set_xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
ax.set_yticks(range(len(corr)), corr.index)
```

## 45.7 Time, categorical, and image axes

- **Dates:** convert with `pd.to_datetime`; plot the datetime column; format with `mdates.ConciseDateFormatter`; `fig.autofmt_xdate()` for rotated labels.
- **Categories:** bar charts, sorted by value; horizontal bars for long labels; top-k + "other" for high cardinality. A thousand string categories produces a thousand ticks.
- **Images:** `ax.imshow(image)` expects `(rows, cols)` or `(rows, cols, channels)`. `origin="upper"` is the default, so images can look upside down; `aspect="auto"` stretches them. Use `cmap="gray"` with `vmin`/`vmax` for grayscale.
- **2D fields:** `pcolormesh` for x/y grids, `contourf` for filled contours.
- **Missing data:** line plots leave gaps; bars and areas fill 0 by default. State which behavior you chose.

```python
ax.plot(df["date"], df["value"])
ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
fig.autofmt_xdate()

ax.imshow(image, cmap="gray", vmin=0, vmax=1, origin="upper", aspect="auto")
```

## 45.8 Pitfalls: chart traps

| Trap | Why it misleads | Fix |
|---|---|---|
| Bar chart y-axis starts above 0 | exaggerates small differences | start bars at 0 |
| Dual y-axes | implies a relationship that may not exist | avoid, or label both scales clearly |
| Pie chart with many slices | angles are hard to compare | sorted bar chart |
| Overplotted scatter | hides density and duplicates | `alpha`, `hexbin`, `hist2d`, sample |
| Histogram bin size | shape changes with the bins | `bins="auto"`, try several |
| Correlation heatmap without fixed scale | weak correlations look strong | `vmin=-1, vmax=1`, diverging colormap |
| Rainbow/jet colormap | perceptual artifacts | `viridis`, `plasma`, `cividis` |
| Unlabeled axes | reader cannot interpret or reproduce | labels, units, sample size |
| 1,000 categorical ticks | unreadable | top-k, horizontal bars, grouping |
| `imshow` origin/aspect | flipped or stretched images | check `origin`, `aspect` |
| Silent NaN handling | gaps vs zeros change the story | state or fill explicitly |
| `plt.savefig` after several figures | saves the wrong figure | `fig.savefig` |

## Quick Reference

| Need | Use |
|---|---|
| Figure and Axes | `fig, ax = plt.subplots(...)` |
| Grid of panels | `plt.subplots(2, 2, sharex=True, sharey=True)` |
| Non-uniform layout | `plt.subplot_mosaic(...)` |
| Labels and title | `ax.set_xlabel`, `ax.set_ylabel`, `ax.set_title` |
| Legend | `ax.legend()` |
| Grid behind data | `ax.grid(alpha=0.3)`, `ax.set_axisbelow(True)` |
| Log scale | `ax.set_yscale("log")` |
| Secondary axis | `ax.twinx()` / `ax.secondary_xaxis(...)` |
| Save | `fig.savefig(path, dpi=150, bbox_inches="tight")` |
| Close | `plt.close(fig)` |
| Box / violin | `ax.boxplot`, `ax.violinplot` |
| 2D density | `ax.hexbin`, `ax.hist2d` |
| Image | `ax.imshow(image, cmap="gray")` |
| Correlation | `df.corr(numeric_only=True)` + `imshow` |
| Scatter matrix | `pd.plotting.scatter_matrix(df)` |
| Date axis | `mdates.ConciseDateFormatter` |
| Missingness | `df.isna().mean()` |
| Label balance | `df[target].value_counts(normalize=True)` |
| Headless backend | `matplotlib.use("Agg")` |

## Theory Summary

- **Figure → Axes → Axis.** The object-oriented API makes that hierarchy explicit; `plt.*` hides it in global state.
- A plot is an argument. Labels, units, scale, and sample size are part of the evidence, not decoration.
- EDA is a sequence of decisions: dtype → missingness → distribution → relationship → outlier → label balance → time/group structure.
- The chart type must match the question. A line implies order, a bar compares categories, a histogram estimates a distribution, a scatter shows a relationship.
- Honest axes matter: bars start at zero, heatmaps use a fixed scale, dual axes need suspicion, and pie charts are usually the wrong tool.
- Save the `fig`, close it, and use `Agg` when there is no display. Matplotlib is the low-level layer; pandas and seaborn wrap it.

## Deliverable

`Phase 2(ML)/STEP 45/step45-matplotlib/`:
- `eda_report.py` — CLI: load a CSV, print shape/dtypes/missing/duplicates, and render a multi-panel report: missingness bar, numeric histograms, correlation heatmap, target balance, and box plots by target. Save it to `reports/eda.png`.
- `test_eda_report.py` — tests on a synthetic CSV: the figure file exists, the expected axes are present, missing counts match, the target balance sums to 1, and the correlation matrix has the right shape.
- `README.md` — usage, what to look for in each panel, and how to adapt the target/column choices.

**Check:** `python eda_report.py data.csv --target label --out reports/eda.png` creates the image and prints the profile; `pytest -q` passes; opening the image shows readable labels, no clipped titles, and a fixed-scale correlation heatmap.
