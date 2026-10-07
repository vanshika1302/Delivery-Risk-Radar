# 09 - Cycle time and status stages

Type: grilling
Status: resolved
Blocked by:

## Question

The glossary defines cycle time as "first move into an in-progress status to final resolution", but the real data says otherwise: in a sample of KAFKA, HDFS and CASSANDRA, 87-96% of tickets never enter a status literally named "In Progress". The usual flow is Open -> Patch Available -> Resolved, and CASSANDRA has about 16 statuses (Triage Needed, Review In Progress, Ready to Commit, Changes Suggested and more). Decide: what counts as the start of active work, whether statuses are mapped into a small set of stages (for example waiting, in progress, in review, ready to merge) per project, how a stage-duration or bottleneck metric handles tickets that skip stages or loop (Reopened, Changes Suggested), and what the SQL analysis therefore reports. Then correct the Cycle time entry in `GLOSSARY.md`. Evidence: [research/08-apache-sample-findings.md](../research/08-apache-sample-findings.md).

## Answer

- **Start of active work:** first entry into any active stage in a per-project status mapping. Tickets that never enter an active stage have an empty cycle time, and the share is reported per project. They stay in the late label, which uses lead time.
- **Stages:** four groups with a mapping table per project: Waiting, Building, In review, Done. Seeded from the sampled statuses and checked against the real status list in the first extraction run. Jira's own three status categories are not used.
- **Loops:** time in a stage is summed across all visits, and review rounds are counted as their own metric. Reopened tickets use the final resolution for lead time.
- **Bottleneck metrics for the SQL phase:** share of lead time per stage by project and issue type; wait from creation to first entry into In review; review rounds. All reported as percentiles, not means, alongside late rate by project and type.
- **Glossary:** Cycle time corrected, and Stage and Review round added in [GLOSSARY.md](../../../GLOSSARY.md).
- Evidence: [research/08-apache-sample-findings.md](../research/08-apache-sample-findings.md)
