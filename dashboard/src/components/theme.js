// Colours: validated categorical slots 1-3 (light and dark steps), plus semantic up/down for "raises / lowers risk".
export const JIRA_REVIEW = ["AMBARI", "HIVE", "HBASE", "CASSANDRA"];
export const GITHUB_REVIEW = ["SPARK", "FLINK", "ARROW", "CAMEL"];

export function palette(dark) {
  return dark
    ? {blue: "#3987e5", orange: "#d95926", aqua: "#199e70", gap: "#55544f", up: "#f0a27a", down: "#4fc196", grid: "#3a3a37"}
    : {blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", gap: "#c9c8c2", up: "#c2410c", down: "#1f7a5a", grid: "#e6e5e0"};
}

export const pct = (x, digits = 0) => `${(x * 100).toFixed(digits)}%`;
export const pts = (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(1)}`;

export const FEATURE_LABEL = {
  assignee_open: "Assigned when filed", has_assignee: "Assigned by day 7", reporter_prior_tickets: "Reporter's earlier tickets",
  reporter_first_time: "First-time reporter", commenters_by_day7: "People commenting", priority_rank: "Priority",
  issue_type: "Issue type", component_count: "Components set", link_count: "Linked tickets", title_length: "Title length",
  description_length: "Description length", project_open: "Open tickets in project", project_key: "Project",
  workflow_family: "Where review happens", peer_n: "Similar tickets to compare", peer_median_lead_days: "Similar tickets: median days",
  peer_late_rate: "Similar tickets: late rate", project_median_lead_days: "Project: median days", project_late_rate: "Project: late rate",
  events_by_day7: "Changes in first week", comments_by_day7: "Comments in first week", days_since_activity_day7: "Days since last activity",
  stage_at_day7: "Stage on day 7", days_in_stage_day7: "Days in current stage", entered_active_by_day7: "Work started by day 7",
  entered_review_by_day7: "In review by day 7", review_rounds_by_day7: "Review rounds so far"
};
export const label = (f) => FEATURE_LABEL[f] ?? f;
