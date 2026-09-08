"use client";

import styles from "@/app/page.module.css";

interface Props {
  disabled: boolean;
  onDownload: () => void;
}

export function DownloadButton({ disabled, onDownload }: Props) {
  return (
    <button className={styles.secondaryButton} disabled={disabled} onClick={onDownload}>
      Download run as Markdown
    </button>
  );
}
