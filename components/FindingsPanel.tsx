"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "@/app/page.module.css";

export function FindingsPanel({ prose }: { prose: string }) {
  return (
    <section data-testid="findings-panel" className={styles.panel}>
      <h2 className={styles.panelTitle}>Findings</h2>
      <div className={styles.markdown}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{prose}</ReactMarkdown>
      </div>
    </section>
  );
}
