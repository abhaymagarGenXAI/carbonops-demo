import { cn } from "@/lib/utils";

type Tone = "success" | "warning" | "destructive" | "info" | "neutral" | "brand";

const toneClass: Record<Tone, string> = {
  success: "bg-success/12 text-success border-success/25",
  warning: "bg-warning/15 text-warning-foreground border-warning/35",
  destructive: "bg-destructive/10 text-destructive border-destructive/25",
  info: "bg-info/10 text-info border-info/25",
  neutral: "bg-muted text-muted-foreground border-border",
  brand: "bg-brand/15 text-brand-foreground border-brand/35",
};

const map: Record<string, Tone> = {
  Approved: "success",
  Validated: "success",
  Operational: "success",
  Active: "success",
  Passed: "success",
  Completed: "success",
  Complete: "success",
  "On Track": "success",
  Calculated: "success",
  Submitted: "info",
  "Under Review": "info",
  "In Progress": "info",
  Open: "info",
  "In Review": "info",
  Standby: "info",
  Draft: "neutral",
  Planned: "neutral",
  "Not Run": "neutral",
  Locked: "neutral",
  Superseded: "neutral",
  Pending: "warning",
  Warnings: "warning",
  Anomaly: "warning",
  "At Risk": "warning",
  "At risk": "warning",
  "Off track": "destructive",
  "On track": "success",
  "No data yet": "neutral",
  "On Hold": "warning",
  "Under Maintenance": "warning",
  "Recalculation Required": "warning",
  Medium: "warning",
  High: "warning",
  Rejected: "destructive",
  Failed: "destructive",
  Missing: "destructive",
  Delayed: "destructive",
  Shutdown: "destructive",
  Suspended: "destructive",
  Critical: "destructive",
  Low: "neutral",
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  const tone = map[value] ?? "neutral";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneClass[tone],
        className,
      )}
    >
      <span className="size-1.5 rounded-full bg-current opacity-70" />
      {value}
    </span>
  );
}
