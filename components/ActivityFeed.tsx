"use client";

import { useEffect, useRef } from "react";
import styles from "@/app/page.module.css";
import { ActivityItem, formatArgs, summarizeToolResponse } from "@/lib/agentEvents";

interface Props {
  items: ActivityItem[];
  startedAt: number | null;
}

function relTime(startedAt: number | null, timestamp: number): string {
  if (!startedAt) return "";
  const s = Math.max(0, Math.round(timestamp - startedAt / 1000));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function ToolCallRow({ item, startedAt }: { item: Extract<ActivityItem, { kind: "tool_call" }>; startedAt: number | null }) {
  const args = formatArgs(item.args);
  return (
    <li className={`${styles.activityItem} ${styles.activityCall}`}>
      <div className={styles.activityHead}>
        <span className={styles.activityIcon} aria-hidden>
          ▶
        </span>
        <span className={styles.activityTime}>{relTime(startedAt, item.timestamp)}</span>
        <span className={styles.activityKind}>tool call</span>
        <code className={styles.activityToolName}>{item.name}</code>
      </div>
      {args.length > 0 && (
        <div className={styles.activityArgs}>
          {args.map((a) =>
            a.block ? (
              <div key={a.label} className={styles.argBlock}>
                <span className={styles.argLabel}>{a.label}</span>
                <pre className={styles.argPre}>{a.value}</pre>
              </div>
            ) : (
              <span key={a.label} className={styles.argInline}>
                <span className={styles.argLabel}>{a.label}:</span> {a.value}
              </span>
            )
          )}
        </div>
      )}
    </li>
  );
}

function ToolResponseRow({
  item,
  startedAt,
}: {
  item: Extract<ActivityItem, { kind: "tool_response" }>;
  startedAt: number | null;
}) {
  const { text, isError } = summarizeToolResponse(item.response);
  return (
    <li className={`${styles.activityItem} ${styles.activityResponse} ${isError ? styles.activityErrorRow : ""}`}>
      <div className={styles.activityHead}>
        <span className={styles.activityIcon} aria-hidden>
          {isError ? "⚠" : "✓"}
        </span>
        <span className={styles.activityTime}>{relTime(startedAt, item.timestamp)}</span>
        <span className={styles.activityKind}>{isError ? "tool error" : "tool response"}</span>
        <code className={styles.activityToolName}>{item.name}</code>
      </div>
      <p className={styles.activityResponseText}>{text}</p>
    </li>
  );
}

function TextRow({ item, startedAt }: { item: Extract<ActivityItem, { kind: "text" }>; startedAt: number | null }) {
  return (
    <li className={`${styles.activityItem} ${styles.activityText}`}>
      <div className={styles.activityHead}>
        <span className={styles.activityIcon} aria-hidden>
          💬
        </span>
        <span className={styles.activityTime}>{relTime(startedAt, item.timestamp)}</span>
        <span className={styles.activityKind}>agent</span>
      </div>
      <p className={styles.activityResponseText}>{item.text}</p>
    </li>
  );
}

function ErrorRow({ item }: { item: Extract<ActivityItem, { kind: "error" }> }) {
  return (
    <li className={`${styles.activityItem} ${styles.activityErrorRow}`}>
      <div className={styles.activityHead}>
        <span className={styles.activityIcon} aria-hidden>
          ⚠
        </span>
        <span className={styles.activityKind}>error</span>
      </div>
      <p className={styles.activityResponseText}>{item.message}</p>
    </li>
  );
}

export function ActivityFeed({ items, startedAt }: Props) {
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [items.length]);

  if (items.length === 0) {
    return <p className={styles.placeholder}>Nothing has happened yet. Start a run to see the agent work.</p>;
  }

  return (
    <ul className={styles.activityList}>
      {items.map((item) => {
        switch (item.kind) {
          case "tool_call":
            return <ToolCallRow key={item.key} item={item} startedAt={startedAt} />;
          case "tool_response":
            return <ToolResponseRow key={item.key} item={item} startedAt={startedAt} />;
          case "text":
            return <TextRow key={item.key} item={item} startedAt={startedAt} />;
          case "error":
            return <ErrorRow key={item.key} item={item} />;
        }
      })}
      <li ref={endRef} aria-hidden />
    </ul>
  );
}
