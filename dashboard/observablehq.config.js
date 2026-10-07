// Delivery Risk Radar dashboard. Everything it shows is precomputed (src/data/*.json, written by `python -m radar.export`),
// so the build needs only Node: the GitHub Pages workflow cannot rerun the 5.8 GB extraction.
export default {
  title: "Delivery Risk Radar",
  root: "src",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Open tickets", path: "/open-tickets"},
    {name: "Model quality", path: "/model-quality"},
    {name: "Method", path: "/method"}
  ],
  style: "style.css",
  head: `<meta name="description" content="Which Apache Jira tickets run late, and why: an analytics-first look at delivery risk.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%232a78d6'/%3E%3Ccircle cx='16' cy='16' r='7' fill='none' stroke='white' stroke-width='3'/%3E%3C/svg%3E">`,
  footer: "Data: The Public Jira Dataset (Apache), snapshot January 2022, CC BY 4.0. Reasons describe associations, not causes.",
  toc: false,
  pager: false,
  search: false
};
