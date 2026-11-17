# Step 46: Machine Learning Fundamentals & Model Evaluation

## The Problem

Suppose you want to predict which customers will cancel a subscription next month. You could write rules yourself, but you do not yet know which patterns reliably predict cancellation. Even after learning those patterns from historical data, a high score can be misleading: if 95% of customers stay, always predicting “stays” gets 95% accuracy. This step explains how learning works, then how to check whether the result is useful on new data.

## Foundational Concepts

### Where this lesson starts

You have covered Python, building applications with existing language models, NumPy (Step 43), pandas (Step 44), and Matplotlib / exploratory data analysis (Step 45). That gives you programming, arrays, tables, and plots. It does **not** mean you already know how a model learns from examples.

This lesson assumes no previous ML training knowledge. It introduces the ideas before the library calls. scikit-learn (Step 47) implements them; feature engineering (Step 48) prepares the inputs; the mathematics is developed in linear algebra (Step 50), probability and statistics (Step 51), calculus and gradient descent (Step 52), and linear / logistic regression (Step 53).

**How to study:** read the foundations and 46.1 first. Then work through 46.2–46.9 in order. The headings use standard topic names, and each numbered section has exact phrases you can search on YouTube. After a video, return to the worked example or checkpoint here; being able to explain or calculate it is the check that you understood it.

### Lesson map

| Section | Topic |
|---|---|
| [46.1](#461-supervised-vs-unsupervised-learning-train--validation--test-split) | Supervised / unsupervised learning, classification / regression, data splits |
| [46.2](#462-overfitting-underfitting-and-the-biasvariance-tradeoff) | Overfitting, underfitting, bias–variance, learning curves |
| [46.3](#463-model-capacity-and-regularization-l1-l2-and-elastic-net) | Model capacity, regularization, L1 / L2 |
| [46.4](#464-cross-validation-and-hyperparameter-search) | Cross-validation and hyperparameter search |
| [46.5](#465-data-leakage-and-leakage-safe-preprocessing) | Leakage and preprocessing |
| [46.6](#466-model-evaluation-metrics) | Classification, ranking, probability, and regression metrics |
| [46.7](#467-class-imbalance-and-decision-threshold-selection) | Class imbalance and thresholds |
| [46.8](#468-baselines-fair-comparisons-and-uncertainty) | Baselines, comparisons, and uncertainty |
| [46.9](#469-error-analysis-misclassifications-data-slices-and-confusion-patterns) | Error analysis |

### 1. Machine learning: learning a rule from examples

In ordinary programming, you write a rule such as “flag customers who called support more than three times.” In **machine learning (ML)**, you choose a learning procedure and provide examples; that procedure uses the examples to produce a rule. The resulting rule is a **model**.

For example, historical customers may show that short subscription history combined with many support calls is associated with cancellation. A trained model can use those inputs to estimate cancellation risk for another customer. You still decide what to predict, which data to supply, and how to judge the result. Learning does not remove those engineering decisions.

ML is useful when examples contain patterns that are difficult to write down reliably by hand. A fixed calculation such as adding sales tax usually needs ordinary code, not a learned model. A prediction also does not establish a cause: predicting cancellation does not prove that giving a discount will prevent it.

### 2. Dataset, samples, features, and target

We will use one running example: at the end of a month, predict whether an active customer will cancel during the **next 30 days**. We use historical months where those 30 days have already passed, so the answers are known.

A **dataset** is a collection of examples. In our tabular dataset, one **sample**, also called an **example** or **observation**, is one row describing one customer at the prediction date.

| customer_id | tenure_months | monthly_charge | support_calls_last_30d | churned_next_30d |
|---|---:|---:|---:|---:|
| A101 | 2 | 80 | 4 | 1 |
| A102 | 24 | 55 | 0 | 0 |
| A103 | 6 | 95 | 3 | 1 |
| A104 | 36 | 50 | 1 | 0 |

**Churn** means cancellation. `tenure_months` means how long the customer has subscribed. A **feature** is an input used to make the prediction: tenure, charge, or the number of past support calls. The **target** is the answer we want to predict: `churned_next_30d`, where `1` means canceled and `0` means stayed. In this lesson, **label** means the recorded target value for an example.

The ID identifies the customer; it is not automatically a useful predictive feature. We keep it for tracking and checking repeated customers, but leave it out of the model inputs here.

The four rows above explain the columns; they are too few to train or evaluate a useful model. Our larger imagined dataset has **10,000 customers, of whom 500 cancel: a 5% churn rate**. “Rate” here means a count divided by the total: `500 / 10_000 = 0.05`.

```python
import pandas as pd

# This small table only demonstrates how to separate inputs from answers.
df = pd.DataFrame({
    "customer_id": ["A101", "A102", "A103", "A104"],
    "tenure_months": [2, 24, 6, 36],
    "monthly_charge": [80, 55, 95, 50],
    "support_calls_last_30d": [4, 0, 3, 1],
    "churned_next_30d": [1, 0, 1, 0],
})
X = df[["tenure_months", "monthly_charge", "support_calls_last_30d"]]
y = df["churned_next_30d"]
print(X.shape, y.shape)  # (4, 3) (4,): four rows, three input columns, four answers.
```

`X` and `y` are conventional variable names, not special Python syntax. `X` holds the feature table; `y` holds the matching answers. Row order must match: the first row of `X` must go with the first answer in `y`.

Real ML data can also be images, audio, or text. A table is simply the easiest starting point. The input / target distinction is the same. See [Google's supervised learning introduction](https://developers.google.com/machine-learning/intro-to-ml/supervised) for this vocabulary.

### 3. Model, parameters, and training

A model stores something learned from the examples. In a simple model, that might be numbers in a formula. For a numerical prediction such as next month's bill, imagine:

```text
predicted_bill = 10 + 2 × usage_hours
```

For 20 usage hours, the prediction is `10 + 2 × 20 = 50`. This is a **linear model**: a weighted sum of inputs plus an intercept. The adjustable numbers `10` and `2` are **parameters**. The `2` is a **weight**, also called a **coefficient**: it controls how much usage affects the prediction. The `10` is the **intercept**, an added starting amount. It is sometimes called a bias term; that is different from the bias in the bias–variance discussion later.

How do we choose those numbers? **Training**, also called **fitting**, uses historical inputs and their answers to find parameter values that make useful predictions. A **learning algorithm** is the procedure that does this. The algorithm is the procedure; the trained model is its result.

Not every model is a weighted formula. A decision tree learns a sequence of questions such as “is tenure below six months?” Its learned questions and cutoffs are part of its fitted state. You will study particular model families later; here the important idea is that training changes the model using examples.

### 4. Loss: how training measures a mistake

A learning procedure needs a numerical way to compare candidate predictions. A **loss function** assigns a penalty to a prediction based on how it differs from the actual answer. Lower loss is better.

If the actual bill is 60 and a candidate model predicts 50, the error `prediction − actual` is `−10`. Its **squared error** is `(-10)² = 100`. Predicting 58 instead gives squared error `4`. Averaging these squared errors over examples gives **mean squared error (MSE)**; “mean” means the arithmetic average.

Many training procedures adjust parameters to reduce an average training loss. This search is called **optimization**. You do not need calculus to understand its purpose: compare predictions with known answers and adjust the model to reduce the penalty. The adjustment mathematics comes in calculus and gradient descent (Step 52).

For cancellation, the answer is a category rather than a bill amount. A model used to predict categories is a **classifier**. It may estimate a cancellation probability: `0.8` means an estimated 80% chance. A common training loss, **log loss**, also called **cross-entropy** in this classification setting, penalizes assigning low probability to the answer that actually happened. Being confidently wrong receives a large penalty. Its formula comes later in probability and statistics (Step 51) and regression (Step 53). See [Google's introduction to loss](https://developers.google.com/machine-learning/crash-course/linear-regression/loss).

### 5. Prediction, evaluation, and generalization

After training, **prediction**, also called **inference**, applies the learned model to inputs. It does not normally change the learned parameters. At the moment you predict a customer's next 30 days, you have the inputs but not the future answer.

**Evaluation** compares predictions with actual answers once those answers are available. A **metric** is a numerical measure of prediction quality. Accuracy is one metric: the fraction of predictions that are correct. A **metric value**, often called a **score**, must name both its metric and the data: “80% recall on validation customers” is meaningful; “the model scored 0.8” is incomplete.

Loss and metric describe different jobs. Training uses a loss to learn parameters; evaluation uses metrics to judge usefulness. They can be the same calculation, as with MSE, or different, as with training on log loss and evaluating cancellation recall.

**Generalization** means making useful predictions on new examples beyond the training examples. Doing well on answers used during training does not establish generalization. A **baseline** is a simple reference prediction you compare against, such as always predicting “stays.” We will use it to give our scores context.

```mermaid
flowchart LR
    A[Historical inputs and known answers] --> B[Training procedure]
    B --> C[Trained model]
    C --> D[Predictions for held-back inputs]
    D --> E[Compare with held-back answers]
    E --> F[Metrics and error inspection]
```

The held-back examples are deliberately excluded from parameter learning. The next section explains how to separate them.

## 46.1 Supervised vs. Unsupervised Learning; Train / Validation / Test Split

> **YouTube searches:** `supervised vs unsupervised learning classification regression`; `train validation test split machine learning`.

### Supervised learning: examples have answers

When you want to predict a particular outcome, training needs examples of that outcome. **Supervised learning** learns from inputs paired with targets. Our churn table is supervised: each historical customer has both input features and a recorded cancellation outcome. “Supervised” refers to the training signal from answers, not someone watching the computer train.

Two main supervised tasks are **classification** and **regression**. Classification predicts a **class**, meaning a category. “Cancels” versus “stays” is **binary classification**, because there are two classes. Predicting one of “billing,” “technical,” or “account” for a support ticket is **multiclass classification**. Predicting several tags that can apply simultaneously is **multilabel classification**.

Regression predicts a numerical quantity: next month's bill, delivery duration, or house price. The distinction is the meaning of the output, not its Python type. Churn encoded as `0` and `1` is still classification because those numbers represent categories. Also, despite its name, *logistic regression* is commonly used for classification; you will learn its mechanism in linear / logistic regression (Step 53).

### Unsupervised learning: find structure without target answers

Sometimes you have customer information but no target column for the question you want to explore. **Unsupervised learning** finds structure in those inputs without using supplied target answers for that task.

**Clustering** groups similar examples: customers with similar spending and usage might form groups. A cluster is a discovered group, not a known answer such as “will cancel.” You must inspect the groups to decide whether they are useful. Customer clustering does not automatically solve churn prediction.

**Dimensionality reduction** represents data using fewer input dimensions. A dimension here is an input coordinate or feature. For example, it might turn 100 measurements into a smaller set of derived coordinates that retain important patterns. This can help with compression or visualization. The algorithms and their evaluation belong to unsupervised learning and PCA (Step 49).

| Question | Learning type | Task |
|---|---|---|
| Will this customer cancel? Historical cancellation answers exist. | Supervised | Classification |
| How much will this customer spend? Historical spending amounts exist. | Supervised | Regression |
| Which customers have similar behavior? No supplied group answers. | Unsupervised | Clustering |
| Can these 100 measurements be represented with fewer coordinates? | Often unsupervised | Dimensionality reduction |

These categories do not cover all ML. **Self-supervised learning** creates training targets from the data itself, such as predicting a hidden word. **Reinforcement learning** learns actions through rewards from interaction. These are orientation terms here; neither is needed for the churn exercise.

### Why training, validation, and test data have separate jobs

If you judge a model on the same answers it learned from, it may look good simply because it adapted to those examples. We therefore **split** the dataset: partition its rows into separate sets.

The **training set** supplies examples used to learn parameters. The **validation set** supplies examples used to make development choices: which model to use, which inputs to include, or which settings to try. The **test set** supplies examples reserved for a final evaluation after those choices are fixed.

The word “test” here differs from Python testing with pytest (Step 13). A code test checks software behavior; a model's test set checks its predictions on held-back examples. You need both, for different reasons.

| Set | Example size from 10,000 rows | Purpose | Can its results change your choices? |
|---|---:|---|---|
| Training | 6,000 | Learn parameters | Yes |
| Validation | 2,000 | Compare candidate choices | Yes |
| Test | 2,000 | Evaluate the selected procedure | No, if keeping it as the final test |

For validation and testing, you supply inputs to the fitted model, then compare its predictions with the held-back answers. The answers are available to the evaluator, but are not passed into parameter fitting.

Think of training as studying worked questions, validation as taking practice exams, and testing as the final exam. Repeatedly choosing models based on validation results can eventually adapt your choices to that practice exam. The test set provides a separate check. If you inspect test errors and then redesign the model, those rows have become development data; a fresh final evaluation is needed for a new independent claim.

The 60/20/20 allocation is an example, not a rule. There must be enough examples of the outcome in each set to evaluate it sensibly. A 20% test set containing only two cancellations cannot establish reliable cancellation recall.

### Random, stratified, group, and time-based splits

A **random split** assigns rows randomly. A **stratified split** additionally keeps class proportions approximately similar: with 5% churn, our 2,000-row validation and test sets each contain about 100 churners. This helps avoid an accidental shortage of one class. A **random seed** fixes the random choices so you can reproduce a split; it does not make that split representative of future use.

Random splitting is suitable when rows are reasonably independent and drawn from conditions matching the intended use. **Independent** here means that a row is not effectively a repeat or close relative of another row across the split.

If customers appear multiple times and the goal is to predict for entirely new customers, use a **group split**: all rows for a customer stay together. If the goal is future prediction, use a **time-based split**: train on earlier dates and evaluate on later dates. Wait until training labels are fully known before the validation prediction date; a 30-day label window can otherwise carry future information across the boundary. Some problems need both group and time restrictions.

**Rule of thumb:** choose the split to imitate the situation in which predictions will be used. Preserving time or group boundaries matters more than preserving exact class percentages.

**Checkpoint:** a model is trained on 6,000 rows. You try five settings and pick one using another 2,000 rows. Which set are those 2,000? **Validation**, even though `.fit()` never used them.

## 46.2 Overfitting, Underfitting, and the Bias–Variance Tradeoff

> **YouTube searches:** `overfitting underfitting bias variance explained`; `learning curves vs validation curves machine learning`.

### Underfitting and overfitting

A model can fail because it misses useful patterns or because it follows the training examples too closely. **Underfitting** means it has not captured enough of the useful relationship between inputs and targets. For example, a rule that gives every customer the same risk ignores differences between customers.

**Overfitting** means adapting too closely to details specific to the training data, including accidental patterns, so performance does not carry over to new examples. Imagine a model that effectively remembers the historical customers instead of learning patterns that apply to other customers.

A useful diagnostic compares the same metric on training and validation data. Suppose we predict a numerical quantity and measure average absolute error in rupees; lower is better:

| Training error | Validation error | Possible interpretation |
|---:|---:|---|
| Rs 500 | Rs 520 | Both poor relative to an Rs 200 baseline: investigate underfitting or data problems |
| Rs 20 | Rs 450 | Large gap: investigate overfitting or different conditions across sets |
| Rs 100 | Rs 120 | Better than the baseline, with a small gap: promising |

These numbers illustrate patterns, not universal cutoffs. Poor train and validation results can also come from wrong labels, uninformative features, or training that did not finish successfully. A large gap can also come from a validation set representing different conditions. Diagnose before choosing a fix.

### What bias and variance mean here

**Bias** is systematic error in the average prediction a learning procedure would make across different training datasets. Intuitively, an overly restrictive model can repeatedly miss the same kind of pattern. **Variance** is how much its predictions change when the training examples change. An overly sensitive model can learn very different rules from slightly different samples.

The **bias–variance tradeoff** describes the tension: increasing flexibility can help capture useful patterns but can also make the model follow accidental ones. This is a useful classical picture, not a law that every increase in complexity must worsen generalization.

**Noise** is variation the available inputs cannot explain, including randomness or measurement errors. If two apparently identical customers make different choices for reasons you never recorded, perfect prediction may be impossible. Under the usual squared-error assumptions, expected prediction error can be decomposed into squared bias, variance, and irreducible noise. This is not a formula for directly adding classification error percentages. The derivation can wait; the diagnostic distinction matters now. See [Stanford's bias–variance and error analysis notes](https://cs229.stanford.edu/section/error-analysis.pdf).

### Learning curves and validation curves

A **learning curve** plots training and validation performance against the number of training examples. You retrain using different amounts of data. If validation improves and the gap shrinks with more data, gathering more similar, useful examples may help. If both curves remain poor, investigate the model, features, labels, and training process.

A **validation curve** instead varies one model setting, such as how flexible the model is. It helps reveal where increased flexibility improves training results while validation results stop improving. Both use held-back development data; neither requires consulting the final test set. See [scikit-learn's curve explanations](https://scikit-learn.org/stable/modules/learning_curve.html).

**Rule of thumb:** investigate whether you are missing patterns, fitting accidental patterns, or facing data limitations. “Add more data” and “use a larger model” solve different problems.

## 46.3 Model Capacity and Regularization: L1, L2, and Elastic Net

> **YouTube searches:** `model capacity regularization explained`; `L1 L2 ridge lasso elastic net intuition`.

### Model capacity: how flexible a rule can be

A rule that is too flexible can chase small accidents in the training examples. **Model capacity** means the range and complexity of patterns a model can represent. A straight-line numerical model has less flexibility than a model that can bend into many shapes. A decision tree allowed to ask many successive questions can isolate very small groups, including individual examples.

More capacity can fix underfitting, but it also creates more opportunities to overfit. Useful capacity depends on the amount and quality of data and on the real relationship being learned.

### Regularization: make complexity pay for itself

**Regularization** discourages certain kinds of complexity during learning. A common approach adds a complexity penalty to training loss:

```text
training objective = average prediction loss + strength × complexity penalty
```

An **objective** is the quantity the training procedure tries to minimize. The model must now improve prediction loss enough to justify a larger penalty. Too strong a penalty can prevent useful patterns from being learned and cause underfitting. See [Google's model complexity lesson](https://developers.google.com/machine-learning/crash-course/overfitting/model-complexity).

For weighted models, **L2 regularization** penalizes the sum of squared weights. With weights `2` and `-3`, that sum is `2² + (-3)² = 13`. **L1 regularization** penalizes the sum of absolute weights: `abs(2) + abs(-3) = 5`. Absolute value removes a number's sign.

Both encourage smaller weights. L2 generally shrinks weights without making them exactly zero. L1 can make some weights exactly zero, removing their contribution in a linear model. **Elastic Net** combines L1 and L2 penalties. **Ridge** and **Lasso** are the conventional names for L2- and L1-penalized linear regression, respectively; L1 and L2 are also used with other model types.

Zeroing a weight is not proof that the underlying feature is irrelevant or has no causal effect. Features can overlap in the information they contain.

### Why feature units matter

Suppose the same bill is recorded as 50 dollars or 5,000 cents. A weighted model can express the same prediction with different weight magnitudes. Penalizing weights without accounting for this would make the result depend on arbitrary units.

**Standardization** rescales each numerical feature by subtracting its training mean and dividing by its training standard deviation. Standard deviation measures spread; the detailed statistics come in Step 51. This puts features on comparable scales for many penalized linear models. Learn these scaling values from training data only and reuse them on other data. Feature engineering (Step 48) develops the implementation.

The regularization strength is a setting you choose, rather than a weight learned directly from examples: a **hyperparameter**. In scikit-learn's Ridge and Lasso, a larger `alpha` means a stronger penalty. In logistic regression, a smaller `C` means stronger regularization. These names are model-specific; do not assume larger always means stronger.

Tree depth limits are another way to restrict capacity. For procedures that learn through repeated updates, **early stopping** stops training when validation performance ceases to improve. You will study those algorithms later; they are alternatives to a weight penalty, not additional prerequisites here.

**Rule of thumb:** choose complexity and regularization using validation results. Stronger regularization can help overfitting, but can worsen underfitting.

## 46.4 Cross-Validation and Hyperparameter Search

> **YouTube searches:** `k fold cross validation stratified explained`; `grid search random search nested cross validation`.

### K-fold cross-validation: rotate the practice exam

One validation split may be unusually easy or difficult. **Cross-validation (CV)** evaluates a learning procedure across several training / validation splits.

In **k-fold cross-validation**, divide development data into `k` chunks called **folds**. For each round, fit a fresh model on all but one fold and evaluate on the remaining fold. With five folds:

| Round | Train on folds | Validate on fold |
|---|---|---|
| 1 | B, C, D, E | A |
| 2 | A, C, D, E | B |
| 3 | A, B, D, E | C |
| 4 | A, B, C, E | D |
| 5 | A, B, C, D | E |

This trains five models; one model does not keep learning across all five rounds. Each row is validation once and training in other rounds. The final test rows participate in **none** of these rounds.

For example, fold accuracies of `0.78, 0.80, 0.79, 0.82, 0.81` average to `0.80`. Their **standard deviation** summarizes how spread out those five results are. Report the fold values or mean and spread. Fold scores share training rows, so their standard deviation is **not** a confidence interval: a statistically justified range describing uncertainty. Formal uncertainty estimation comes in probability and statistics (Step 51).

Use **stratified k-fold** for suitable classification data to keep class proportions similar. Use group-aware or time-aware validation when those boundaries matter. Ordinary shuffled folds do not become appropriate merely because you average their results.

### How CV fits with the earlier three-way split

Two useful workflows are:

1. **Simple holdout:** 60% training, 20% validation, 20% test. Fit on training, make choices on validation, evaluate the fixed choice on test.
2. **CV:** reserve 20% test, then use the remaining 80% as development data. Rotate training and validation roles **inside that 80%**. Select settings, refit the selected procedure on that 80%, then evaluate on test.

CV can replace a fixed validation split. It does not replace the need for an independent final evaluation. If you also reserve data to choose an action threshold, keep that role explicit. See [scikit-learn's cross-validation guide](https://scikit-learn.org/stable/modules/cross_validation.html).

### Grid search, random search, and selection bias

**Hyperparameter search** compares settings such as different regularization strengths. Unlike parameters, these settings are chosen outside an individual model fit.

A **grid search** tries every combination in specified lists. Three strengths and two other settings give six candidates; five-fold CV requires 30 fits. A **random search** samples a fixed number of combinations from specified choices or ranges, letting you control the search budget.

Trying many candidates increases the chance that the winner benefited from validation luck. This is **selection bias**: the selection process makes the winning development score look more favorable. Do not report the best tuning score as though it were an independent test result.

**Nested cross-validation** puts a tuning loop inside each outer evaluation split. The inner loop chooses settings; the outer held-back fold evaluates that choice. It is useful when estimating a whole tuning procedure, especially without a separate test set. Know its purpose now; implementation can wait until scikit-learn (Step 47).

**Rule of thumb:** keep test data outside the entire selection procedure, including preprocessing and threshold choice. More CV fits cannot repair a dishonest split.

## 46.5 Data Leakage and Leakage-Safe Preprocessing

> **YouTube searches:** `data leakage target leakage machine learning`; `pipeline preprocessing cross validation leakage`.

### Leakage: using information you would not really have

An evaluation can look excellent if the model has access to clues that would not exist when it makes a real prediction. **Data leakage** means information improperly crosses the boundary between what development is allowed to use and what should be unavailable.

Our prediction is made at the end of the month about cancellation during the next 30 days. `support_calls_last_30d` can be valid because those calls happened before prediction. `cancellation_reason`, recorded after cancellation, cannot be a valid input. That is **target leakage**: the feature reveals the outcome, directly or indirectly.

Other leakage routes include repeated examples across sets, future transactions included in historical features, and choosing settings based on the test results. High performance is not automatically suspicious, but implausibly good performance deserves an information-timing check.

### Preprocessing can learn from data too

**Preprocessing** means preparing inputs before the predictive model uses them. **Imputation** fills missing values, perhaps with the training median; the median is the middle value after sorting. Standardization learns the training mean and spread. Both preparations learn values from data, even though they do not learn the churn target directly.

Suppose a numerical training column contains `[10, 20]`, and a held-back row contains `90`. The training mean is `15`. Calculating the mean on all three rows gives `40`, letting the held-back row influence the preparation. Instead, learn `15` from training and use that same value when preparing validation or test inputs.

The general distinction is **fit** versus **transform**. Fitting a preparation step learns its values. Transforming applies previously learned values to inputs. Validation and test data may be transformed using training values; they must not supply new fitting values.

A **pipeline** chains preparation steps and the predictive model into one procedure. During a fit, each preparation step learns from the allowed training rows. During prediction, those learned preparations are applied before the model predicts. During CV, a fresh pipeline must be fitted within each training fold; preparing the full development dataset before CV still leaks across its validation folds. See [scikit-learn's common pitfalls guide](https://scikit-learn.org/stable/common_pitfalls.html).

```text
Correct for every validation round:
training rows   → learn preparation values → fit model
validation rows → apply those same values → predict → evaluate
```

A pipeline does not know that a cancellation column comes from the future. You must also check feature availability, duplicates, and group / time boundaries yourself.

### Connecting this to your pandas and EDA work

Cleaning and exploratory data analysis remain useful, but learn model-development decisions from the training portion. Selecting features because they correlate with test answers also uses test information. Establishing a file schema or applying a fixed unit conversion does not require fitting statistics; the issue is information flow, not whether every line of pandas must follow a split.

**Rule of thumb:** for every input and learned preparation value, ask, “Could this have been available using only the allowed history and training rows?”

## 46.6 Model Evaluation Metrics

> **YouTube searches:** `confusion matrix accuracy precision recall F1 explained`; `ROC AUC vs precision recall average precision`; `probability calibration reliability diagram`; `MAE MSE RMSE R squared explained`.

### Positive class, probabilities, and decision thresholds

Different mistakes have different consequences, so “percent correct” is not enough. First choose the event you want to detect. In churn prediction, the **positive class** is cancellation (`1`); the **negative class** is staying (`0`). Positive means “the designated event,” not “a good outcome.”

A classifier may estimate a cancellation probability for each customer. A **decision threshold** converts that estimate into a class prediction. With threshold `0.5`, our rule is “predict cancellation when the estimated probability is at least 0.5.” An estimate of `0.7` becomes class `1`; `0.2` becomes class `0`. This lesson explicitly uses `>=` for ties; library defaults can differ at exact ties.

These are two different outputs: a probability estimate such as `0.7`, and a class decision such as `1`. Some models instead provide a ranking score without a probability interpretation. Do not assume every model output is a probability.

### Confusion matrix: count the four possible outcomes

A **confusion matrix** counts how actual and predicted classes compare. Imagine evaluating 1,000 customers: 50 actually cancel and 950 stay. At one chosen threshold, we get:

| Actual outcome | Predicted cancel | Predicted stay | Total |
|---|---:|---:|---:|
| Canceled | 30 true positives (TP) | 20 false negatives (FN) | 50 |
| Stayed | 70 false positives (FP) | 880 true negatives (TN) | 950 |
| Total | 100 | 900 | 1,000 |

A **true positive** correctly identifies a cancellation. A **false positive** raises an unnecessary cancellation alert. A **false negative** misses a cancellation. A **true negative** correctly predicts a customer will stay. “True / false” says whether the prediction was right; “positive / negative” says what the model predicted.

Always read axis labels: some diagrams transpose this table. scikit-learn's binary matrix with class order `[0, 1]` has rows for actual classes, columns for predicted classes, and values `[[TN, FP], [FN, TP]]`.

### Accuracy, precision, recall, specificity, and F1

**Accuracy** asks, “What fraction of all predictions were correct?” Here it is `(TP + TN) / total = (30 + 880) / 1,000 = 91%`. Yet predicting “stays” for everyone gives 95%. Does that make the model worse? It is worse at accuracy, but it identifies 30 cancellations that the always-stay rule misses. Whether that is useful depends on the cost of those 70 false alerts.

**Precision** asks, “Of the customers we flagged, how many actually canceled?” Here `TP / (TP + FP) = 30 / 100 = 30%`. This matters if each alert consumes a costly phone call or offer.

**Recall**, also called **sensitivity** or **true positive rate (TPR)**, asks, “Of the customers who canceled, how many did we catch?” Here `TP / (TP + FN) = 30 / 50 = 60%`. This matters if missing a cancellation is expensive.

Precision starts from the **predicted positives**; recall starts from the **actual positives**. This is the same broad “how much retrieved material was useful?” versus “how much useful material did we retrieve?” distinction you encountered in retrieval quality (Step 26), applied to customers rather than documents.

**Specificity**, or **true negative rate**, is `TN / (TN + FP) = 880 / 950 ≈ 92.6%`. It measures how many actual stayers avoid a false alert. **Balanced accuracy** averages recall and specificity, giving the two classes equal weight: approximately `76.3%` here. It helps expose the failure of an always-stay rule, whose balanced accuracy is 50% when both classes are present.

**F1** combines precision and recall:

```text
F1 = 2 × precision × recall / (precision + recall)
   = 2 × 0.30 × 0.60 / (0.30 + 0.60)
   = 0.40
```

This combination is called a harmonic mean. It is held down when either precision or recall is low. F1 does not use true negatives and does not encode a particular financial cost. Use it when that precision–recall balance fits the task, not as an automatic replacement for accuracy. See [Google's classification metrics lesson](https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall).

If no customers are predicted positive, precision's denominator is zero. If there are no actual positives, recall's denominator is zero. State how your evaluation handles these undefined cases; a library's displayed zero does not make the missing evidence disappear.

### ROC curve and ROC-AUC: evaluate ranking across thresholds

One threshold gives one confusion matrix. To see how behavior changes, move the threshold and recompute the counts.

The **ROC curve** (receiver operating characteristic curve) plots true positive rate (recall) against **false positive rate (FPR)**, where `FPR = FP / (FP + TN)`. In our example, FPR is `70 / 950 ≈ 7.4%`. This differs from “what fraction of alerts were false,” which is `70 / 100 = 70%`.

**AUC** means area under a curve. **ROC-AUC** summarizes the ROC curve into a ranking measure: the chance a randomly chosen positive receives a higher score than a randomly chosen negative, counting ties as half a success. A perfect ranking has ROC-AUC `1`; an uninformative ranking has a reference value of `0.5`.

It does not mean “85% of decisions are correct” when ROC-AUC is `0.85`. It does not select your threshold or establish that estimated probabilities are trustworthy. See [Google's ROC and AUC explanation](https://developers.google.com/machine-learning/crash-course/classification/roc-and-auc).

With many negatives, even a small false positive rate can produce many false alerts. The ROC calculation is not mathematically invalid for imbalanced data; it may simply hide the alert-volume problem you care about. Inspect precision and recall too.

### Precision–recall curve, PR-AUC, and average precision

A **precision–recall (PR) curve** plots precision against recall as the threshold changes. It focuses on how many positives you find and how reliable your alerts are, making it useful for rare events.

**Prevalence** is the fraction of examples that are positive: 5% in our larger churn example. A ranking with no useful signal has a precision reference level of 5%. An effective model should concentrate more churners near the top of its ranking.

**PR-AUC** is an area under a precision–recall curve. **Average precision (AP)** is a related summary that weights precision by successive increases in recall. AP and the area calculated by connecting points with straight lines are **not the same calculation**. scikit-learn's `average_precision_score` computes AP; label its output “average precision,” not silently “PR-AUC.” See the [official average precision definition](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html).

For a constant score assigned to every customer, AP equals the evaluated positive fraction. AP depends on prevalence, so comparisons across datasets with different churn rates require care. Like ROC-AUC, it summarizes ranking across thresholds; you still need metrics at the threshold you will use.

### Probability calibration: does 20% really mean about 20%?

Ranking people correctly does not ensure that a probability estimate has the right numerical meaning. **Calibration** describes agreement between estimated probabilities and observed frequencies. Among many customers assigned probabilities near `0.2`, about 20% should cancel if those estimates are well calibrated for that population.

A **calibration curve**, also called a **reliability diagram**, groups similar probability estimates, then compares their average estimate with their observed cancellation rate. Groups need enough examples; a group of three customers cannot establish reliable calibration.

The binary **Brier score** averages `(estimated_probability − actual_label)²`. For an actual cancellation, predicting `0.8` contributes `(0.8 − 1)² = 0.04`; predicting `0.1` contributes `0.81`. Lower is better. Log loss also evaluates probability quality and penalizes confident mistakes strongly.

Neither Brier score nor log loss measures calibration alone: ranking ability and other factors influence them too. Inspect a calibration curve when probability meaning matters. If you learn a probability correction, that fitting must use suitable held-back development data or CV, never the final test set. See [scikit-learn's probability calibration guide](https://scikit-learn.org/stable/modules/calibration.html).

### Regression metrics: when the target is a quantity

Class counts do not measure how far a predicted bill is from the actual amount. For regression, begin with errors. Suppose actual bills are `[100, 200, 300]` and predictions are `[110, 190, 330]`. Prediction errors are `[10, -10, 30]`.

**Mean absolute error (MAE)** averages their absolute sizes: `(10 + 10 + 30) / 3 ≈ 16.67`. It says the average absolute miss is about 16.67 in the bill's units.

**Mean squared error (MSE)** averages squared errors: `(100 + 100 + 900) / 3 ≈ 366.67`. Squaring makes a large miss contribute disproportionately. **Root mean squared error (RMSE)** takes the square root of MSE: approximately `19.15`, restoring the target's original units.

**R²**, pronounced “R squared,” compares the sum of squared model errors with the sum obtained by predicting the mean of the evaluated targets. Here that mean is `200`:

```text
R² = 1 − sum of squared model errors / sum of squared deviations from target mean
   = 1 − 1,100 / 20,000
   = 0.945
```

A perfect prediction gives `1`; predicting that evaluated mean gives `0`; worse squared error can give a negative R². It is not “94.5% accurate.” Constant-target datasets make the usual denominator zero, requiring special handling. Also keep a practical baseline that learns its constant from **training data**; the evaluated mean inside the R² definition is a mathematical reference, not a deployable prediction rule.

**Mean absolute percentage error (MAPE)** expresses errors relative to actual values, but becomes undefined or unstable when actual values are zero or near zero. Do not choose it merely because percentages sound intuitive. See [scikit-learn's regression metric definitions](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics).

### Multiclass metrics and averaging

For more than two classes, inspect each class's precision and recall. **Support** is the number of actual examples of a class. A **macro average** gives each class equal weight; a **weighted average** weights by support and can conceal weak rare-class performance. A **micro average** pools the underlying counts before calculating the metric. For single-label multiclass classification over all classes, micro precision / recall / F1 equal accuracy.

**Rule of thumb:** choose a primary metric from the decision you must make, then inspect complementary metrics. Accuracy is suitable only when its equal treatment of mistakes fits the task; balanced class counts alone do not guarantee that.

**Checkpoint:** in the 1,000-customer example, which denominator gives recall: 100 alerts or 50 actual cancellations? **50 actual cancellations.** Precision uses the 100 alerts.

## 46.7 Class Imbalance and Decision Threshold Selection

> **YouTube searches:** `imbalanced classification class weights oversampling undersampling`; `classification threshold tuning precision recall tradeoff`.

### Why imbalance changes the problem

**Class imbalance** means some classes occur much more often than others. In our dataset, staying is the **majority class** and cancellation is the **minority class**. An always-stay rule gets 95% accuracy but 0% cancellation recall. This is why you must inspect both the outcome counts and the mistakes that matter.

Imbalance is not automatically something to remove. The 5% rate may accurately describe real use. Evaluation data should represent that use; artificially balancing test data changes the meaning of precision and probability-quality measurements.

### Threshold tuning changes decisions without retraining

Lowering the threshold flags more customers. On fixed scores it cannot reduce recall, but it can add false positives. Precision often falls, although it need not decrease at every individual threshold. The model's ranking and probability estimates are unchanged; the action rule changed.

Suppose the following counts were measured on the same 1,000 validation customers with 50 actual cancellations:

| Threshold | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| 0.5 | 30 | 70 | 20 | 880 | 30% | 60% |
| 0.2 | 45 | 180 | 5 | 770 | 20% | 90% |

Which is better depends on what happens after an alert. If an unnecessary alert costs Rs 10 and a missed cancellation costs Rs 200, a simplified error-cost calculation gives:

```text
cost = 10 × FP + 200 × FN
threshold 0.5: 10 × 70  + 200 × 20 = Rs 4,700
threshold 0.2: 10 × 180 + 200 × 5  = Rs 2,800
```

Under these assumptions, `0.2` has lower estimated cost despite lower precision. Those costs are invented for the exercise. A real retention decision also needs evidence about whether an intervention works, the cost of contacting true positives, and operational limits. Predicting churn alone does not estimate the benefit of an offer.

Choose the threshold on validation data, freeze it along with the model, then evaluate on test. If only 100 calls can be made, examine precision and recall among the top 100 ranked customers instead of assuming an unconstrained threshold is practical. See [scikit-learn's threshold tuning guide](https://scikit-learn.org/stable/modules/classification_threshold.html).

### Class weights and resampling change training

**Class weights** give examples from different classes different influence in the training loss. Higher positive-class weight makes errors on actual churners more costly to the learning procedure. It is not the same as choosing an action threshold, and it does not guarantee a better result.

**Resampling** changes which training examples are used or how often they appear. **Oversampling** repeats or generates minority-class examples; **undersampling** removes some majority-class examples. Repeating rows adds emphasis, not new independent information; removing rows discards information.

Fit resampling only within the training portion of each validation round. Resampling before a split can put copies or related generated examples on both sides. Weighting and resampling can also change probability estimates, so recheck calibration on data reflecting real use.

**Rule of thumb:** begin with a correct split, a baseline, and suitable metrics. Compare threshold changes and training changes on validation data rather than assuming imbalance requires one particular fix.

## 46.8 Baselines, Fair Comparisons, and Uncertainty

> **YouTube searches:** `dummy classifier baseline machine learning`; `model evaluation uncertainty paired comparison`.

### Establish a useful reference

A model score has little meaning without a comparison. A **dummy baseline** makes predictions without learning relationships between features and targets. For classification, always predicting the training majority class gives a basic class-decision baseline. Predicting the training positive fraction for everyone gives a probability baseline with no ability to rank customers.

For regression, always predicting the training mean is a useful squared-error baseline. The training median is a useful absolute-error baseline. A simple business rule can be a stronger reference, such as flagging customers with at least three recent support calls. A simple trained model can then provide another comparison.

For 5% churn, the constant majority-class rule has 95% accuracy and zero churn recall. A constant probability score has ROC-AUC `0.5` when both classes are present, and AP equal to the evaluated prevalence. “Beat the baseline” must therefore name the metric and constraints. Predicting cancellation for everyone improves recall to 100% while producing many false alerts.

### Compare under the same conditions

Use identical evaluation rows, target definitions, and metric calculations. Choose each candidate's settings and threshold using development data only. If preprocessing differs by model, that is allowed, but each complete procedure must be fitted without access to its evaluation rows.

For an alert system, compare recall at a similar alert budget or compare a justified cost calculation. A more complex model also costs effort to maintain; a small score increase may not justify it.

### A measured improvement can be sampling luck

An evaluation contains a finite sample of possible future cases. If test data has 100 actual churners, catching one additional churner changes recall by one percentage point. A tiny improvement needs more evidence than a single printed decimal.

Use paired comparisons: measure both candidates on the same validation splits and inspect their differences. Consistent gains across suitable splits are more convincing than one lucky result. Fold spread alone neither proves nor disproves an improvement. Formal tools such as **bootstrap resampling**, which repeatedly samples evaluation examples with replacement to assess variability, belong with sampling uncertainty in probability and statistics (Step 51); group and time dependencies require appropriate versions.

Even a clean test result estimates performance under the represented conditions. **Distribution shift** means future data differs from the development data, such as a new pricing policy changing cancellation behavior. An untouched test set does not guarantee performance after such a change.

**Rule of thumb:** claim a specific improvement under specific evaluation conditions, with sample counts and uncertainty in view. Avoid claiming universal model quality from one number.

## 46.9 Error Analysis: Misclassifications, Data Slices, and Confusion Patterns

> **YouTube searches:** `machine learning error analysis data slices`; `classification confusion matrix error analysis`.

### Inspect examples to find the next useful change

A score tells you how much error occurred; it rarely tells you what to fix. **Error analysis** means examining predictions and the examples behind them to identify patterns in failure. A **misclassification** is a wrong category prediction: a false positive or false negative in our binary example.

Start with validation errors. Put the input features, actual answer, probability estimate, and predicted class into a table. Inspect missed cancellations, false alerts, and confidently wrong predictions. Check whether the label is correct and whether features were recorded correctly before assuming a more complex model is needed.

A **data slice** is a subset defined by a property such as contract type, tenure range, or month. Calculate the same metrics by slice, together with the number of examples and actual positives. Good overall recall can conceal poor recall for newer customers. A slice containing two churners is too small for a stable conclusion.

| Pattern on validation data | Next investigation |
|---|---|
| False negatives concentrated among new customers | Too few similar training examples? Useful history unavailable? |
| Confidently wrong predictions near a policy change | Has the relationship between inputs and outcomes changed? |
| Many errors with a missing charge value | Data collection or missing-value handling problem? |
| Several target labels are incorrect | How were labels collected, and can that process be fixed? |
| Two ticket classes repeatedly confused | Are category definitions distinct and consistently applied? |

For regression, inspect **residuals**: differences between actual and predicted values. State the sign convention; `actual − predicted` is common. Plot them against predicted values, important features, and time using Matplotlib. Patterns can reveal systematic errors, such as consistently underpredicting high bills.

After the final test evaluation, you may inspect errors to report limitations. If those findings drive another development cycle, acknowledge that reuse and obtain fresh held-back evidence for the next final claim.

**Rule of thumb:** each analysis should lead to a concrete hypothesis you can check on development data. An average is a starting point, not an explanation.

## Pitfalls

| Symptom or mistake | What to investigate or do |
|---|---|
| New customer predictions fail despite near-perfect historical scores | Check outcome timing, repeated rows, and inappropriate splits before trusting the score |
| Fitting the scaler or imputer on the full dataset | Refit preparation inside each training split or CV fold |
| Running CV on all rows after reserving test data | Run selection only within development data; keep test separate |
| High accuracy with no cancellations detected | Inspect class counts, baseline recall, and false negatives |
| Treating a large train–validation gap as a complete diagnosis | Check overfitting, data differences, and evaluation consistency |
| Choosing every setting and threshold on test results | Treat those rows as development data; obtain a fresh final check |
| Calling AP “PR-AUC” without identifying the calculation | Label `average_precision_score` as average precision |
| Calling Brier score a pure calibration measure | Also examine the reliability diagram and group sizes |
| Balancing validation or test data to “fix” imbalance | Preserve or justify the evaluation population; resample training only |
| Reporting ROC-AUC or AP from predicted 0/1 labels | Supply probability estimates or ranking scores for ranking metrics |
| A high score on a tiny rare-class sample | Report actual positive counts and avoid strong conclusions |
| Treating a video or definition as completed learning | Explain a worked example and produce the exercise below |

## Quick Reference

| Term | Meaning / question |
|---|---|
| Features `X`; target `y` | Inputs supplied for prediction; answer to predict |
| Parameter; hyperparameter | Learned fitted value; setting chosen outside an individual fit |
| Training; inference | Learn a model from examples; apply the learned model |
| Loss; metric | Penalty used for learning; calculation used to judge prediction quality |
| Supervised; unsupervised | Learn using supplied targets; find structure without supplied targets for that task |
| Classification; regression | Predict a category; predict a quantity |
| Train / validation / test | Learn / choose / final evaluation |
| Underfitting; overfitting | Miss useful patterns; adapt too closely to training-specific details |
| Regularization | Discourage complexity during learning |
| Cross-validation | Repeatedly fit and evaluate on different allowed splits |
| Leakage | Use information that should be unavailable to development or prediction |
| Precision; recall | Correct positives / predicted positives; correct positives / actual positives |
| ROC-AUC; AP | Two summaries of ranking, with different emphasis |
| Calibration | Agreement between estimated probabilities and observed rates |
| Threshold | Rule converting a score or probability into a class decision |
| MAE; RMSE | Average absolute miss; square root of average squared miss |
| Baseline; slice | Reference prediction; subgroup inspected separately |

The following names are for recognizing scikit-learn tutorials in **Step 47**, not APIs you must already know:

| Idea from this lesson | Library name you will meet |
|---|---|
| Split rows; stratified CV | `train_test_split`; `StratifiedKFold` |
| Group / chronological validation | `GroupKFold`; `TimeSeriesSplit` |
| Chain preparation with a model | `Pipeline` / `make_pipeline` |
| Fill missing values; standardize | `SimpleImputer`; `StandardScaler` |
| Compare settings with CV | `GridSearchCV`; `RandomizedSearchCV` |
| Constant baselines | `DummyClassifier`; `DummyRegressor` |
| Classification counts and metrics | `confusion_matrix`; `classification_report` |
| Ranking metrics | `roc_auc_score`; `average_precision_score` |
| Probability quality | `brier_score_loss`; `log_loss`; `calibration_curve` |
| Regression errors | `mean_absolute_error`; `root_mean_squared_error`; `r2_score` |

## Theory Summary

A model learns a relationship from examples; evaluation checks how useful its predictions are beyond those examples. Define the prediction date, available inputs, target, and intended use before choosing a model.

Keep parameter learning, development choices, and final evaluation separate. That separation applies to preparation, model selection, calibration, and action thresholds. The split must reflect time and repeated entities when those affect real use.

Model flexibility and regularization influence which patterns can be learned. Compare training and validation behavior to form a diagnosis, then inspect examples rather than prescribing a fix from one score.

Different metrics answer different questions: correct decisions, detected events, reliable alerts, useful rankings, trustworthy probabilities, or numerical error sizes. Compare with a meaningful baseline under the same conditions. Sample size, data quality, and future changes limit what any result can establish.

## Deliverable

**Build next:** `step46-eval/evaluate_predictions.py`, a small evaluator for already supplied predictions. This is the Step 46 learning exercise; it does not require implementing a training algorithm or completing the scikit-learn step early. The file is not created by these notes.

Start with the complete Python example below. The supplied probabilities are invented so you can concentrate on evaluation. This script does **not** train a model or establish real predictive performance.

```python
# Ten examples: 1 means canceled, 0 means stayed.
y_true = [1, 0, 0, 1, 0, 0, 1, 0, 0, 0]
# Invented cancellation probabilities, in the same row order as y_true.
probabilities = [0.90, 0.80, 0.60, 0.55, 0.40, 0.30, 0.25, 0.20, 0.10, 0.05]


def evaluate(actual, predicted):
    # Count the four combinations of actual answer and class decision.
    tp = sum(a == 1 and p == 1 for a, p in zip(actual, predicted))
    fp = sum(a == 0 and p == 1 for a, p in zip(actual, predicted))
    fn = sum(a == 1 and p == 0 for a, p in zip(actual, predicted))
    tn = sum(a == 0 and p == 0 for a, p in zip(actual, predicted))
    # In this exercise, zero denominators display 0.0 by explicit convention.
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "accuracy": (tp + tn) / len(actual),
        "precision": precision, "recall": recall, "F1": f1,
    }


for threshold in [0.5, 0.2]:
    # Convert the same probabilities into different action decisions.
    predictions = [int(p >= threshold) for p in probabilities]
    print(threshold, evaluate(y_true, predictions))

# Compare with a rule that predicts everyone stays.
print("always stays", evaluate(y_true, [0] * len(y_true)))
```

Expected counts are `(TP=2, FP=2, FN=1, TN=5)` at `0.5`, and `(TP=3, FP=5, FN=0, TN=2)` at `0.2`. The always-stay baseline gets 70% accuracy on **this ten-row example**, whose positive fraction is 30%; do not confuse it with the larger 5%-churn example. Before reusing the evaluator on files, validate nonempty, equally sized inputs and binary class values; `zip` silently truncates mismatched inputs.

To finish the exercise, add a Brier-score calculation from the probabilities and a printed error-cost comparison using the costs in 46.7. Save a short `step46-eval/README.md` explaining which threshold you prefer under those assumptions, and why this ten-row calculation cannot prove generalization. Commit your finished exercise when you have worked through it.

Before moving to scikit-learn (Step 47), answer these without copying definitions:

1. Predicting a bill versus predicting whether a bill will be paid: which is regression, which is classification?
2. Why does validation influence a model choice even when its rows are never passed to fitting?
3. Why does filling missing values using the full dataset mean leak information?
4. Can a model have good ROC-AUC and still produce too many false alerts?
5. Why does a 95% accurate always-stay rule fail to demonstrate useful churn detection?
6. If you want to test future customers, what goes wrong with mixing future rows into training?

Answers: (1) quantity → regression; category → classification. (2) You select settings using its results. (3) Held-back values influence learned preparation. (4) Yes; ranking performance does not guarantee suitable decisions at an operating threshold. (5) It catches no churners and merely matches the class imbalance. (6) The evaluation no longer imitates predicting from available history.

### Sources and further study

Reviewed November 2026. These are references for checking explanations; you do not need to read them all before starting the lesson. The retrieved scikit-learn documentation identifies itself as version 1.9.1; the exercise above uses only Python's built-in features.

- [Google: introduction to supervised learning](https://developers.google.com/machine-learning/intro-to-ml/supervised) — inputs, targets, training, evaluation, inference.
- [Google: Machine Learning Crash Course](https://developers.google.com/machine-learning/crash-course) — structured visual lessons and exercises.
- [Stanford CS229: bias–variance and error analysis](https://cs229.stanford.edu/section/error-analysis.pdf) — the mathematical background to 46.2.
- [scikit-learn: model selection and evaluation](https://scikit-learn.org/stable/model_selection.html) — splitting, tuning, thresholds, metrics.
- [External curriculum: What Is Machine Learning](https://github.com/rohitg00/ai-engineering-from-scratch/blob/main/phases/02-ml-fundamentals/01-what-is-machine-learning/docs/en.md) and [Model Evaluation](https://github.com/rohitg00/ai-engineering-from-scratch/blob/main/phases/02-ml-fundamentals/09-model-evaluation/docs/en.md) — cross-checked for scope. Their maths and earlier-model prerequisites are not assumed here.
