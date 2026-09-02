CREATE TABLE render_task_attempts
(
    task_id            String,
    job_id             LowCardinality(String),
    shot_id            LowCardinality(String),
    frame_number       UInt16,
    node_id            LowCardinality(String),
    node_group         LowCardinality(String),
    attempt            UInt8,
    status             LowCardinality(String),
    started_at         DateTime,
    ended_at           DateTime,
    duration_sec       UInt32 MATERIALIZED dateDiff('second', started_at, ended_at),
    error_class        LowCardinality(Nullable(String)),
    error_text         Nullable(String),
    peak_mem_gb        Float32,
    mem_allocated_gb   Float32,
    renderer_version   LowCardinality(String),
    uses_hair_shader   Bool,
    asset_refs         Array(String),
    submitted_by       LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY (started_at, node_group, shot_id, task_id, attempt);

CREATE TABLE farm_nodes
(
    node_id            LowCardinality(String),
    node_group         LowCardinality(String),
    mem_gb             UInt16,
    cpu_cores          UInt8,
    renderer_version   LowCardinality(String),
    online             Bool
)
ENGINE = MergeTree
ORDER BY (node_group, node_id);

CREATE TABLE past_incidents
(
    incident_id        String,
    occurred_on        Date,
    title              String,
    error_class        LowCardinality(String),
    symptom_summary    String,
    dimension_signature String,
    root_cause         String,
    remediation        String,
    outcome            LowCardinality(String),
    time_to_resolve_min UInt16
)
ENGINE = MergeTree
ORDER BY (occurred_on, incident_id);
