# 10 - Explainability

Type: grilling
Status: resolved
Blocked by:

## Question

What does "explain why" mean per ticket, given the model decisions (logistic regression baseline, gradient boosting main model, two prediction points, pooled across projects)? Decide: the method (for example SHAP values for the boosting model, coefficients for the logistic regression, permutation importance globally, or plain-language reason codes), what a single ticket explanation shows (top contributing features, direction and size, comparison with the peer group), the global explanation (what drives lateness across projects and per project), how to translate features into readable reasons ("no assignee after 7 days", "priority below the project norm"), how to precompute explanations for a static dashboard, and how to check that explanations are stable and not misleading (for example correlated features).

## Answer

- **Method:** per-ticket SHAP values on the gradient boosting model, and coefficients for the logistic regression baseline. To verify at build time: whether SHAP's tree explainer supports scikit-learn's `HistGradientBoostingClassifier`. Fallbacks: SHAP's model-agnostic explainer, or a different boosting library.
- **Per ticket:** the probability of late, the top 5 contributing features with direction and size, each as a plain-English reason, and the ticket's value next to its peer group's typical value.
- **Global:** overall importance, top drivers per project, and plots of how risk changes with 3 or 4 key features.
- **Readability:** features grouped into reason themes (Ownership, Scope, Workload, History), with theme totals and individual features both shown. The spec holds a dictionary turning each feature and value range into a readable sentence.
- **Serving and checks:** the pipeline precomputes the top 5 reasons for every scored ticket and ships JSON; no model runs in the browser. Explanations are checked for stability across bootstrap samples and time folds. The dashboard states that explanations describe model associations, not causes.
- Vocabulary: Reason theme added in [GLOSSARY.md](../../../GLOSSARY.md).
