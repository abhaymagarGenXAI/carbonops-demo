import { useState } from "react";
import { useAlerts, useValidationRules } from "@/hooks/useApi";
import { alertLink, alertLinkLabel } from "@/lib/alerts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  ClipboardList,
  FileStack,
  Leaf,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/status-badge";
import { PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { useStore } from "@/lib/store";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function DashboardPage() {
  usePageMeta("Operations Workspace — CarbonOps AI", "Daily operational workspace for decarbonization teams: pending submissions, approvals, AI alerts, data quality issues and reporting deadlines.");
  const { currentPeriod: openPeriod, facilities, facilityName, recentActivity, reportingPeriods, role } = useStore();
  const [picked, setPicked] = useState<string | null>(null);
  const currentPeriod = picked && reportingPeriods.some((p) => p.period === picked) ? picked : openPeriod; // viewed period
  const calendarMonth = new Date().toISOString().slice(0, 7);

  const { submissions, documents, initiatives, emissions, assets } = useStore();

  const currentSubs = submissions.filter((s) => s.month === currentPeriod);
  const sent = facilities.filter((f) => currentSubs.some((s) => s.facilityId === f.id && s.status !== "Draft")).length;
  const due = facilities.length - sent; // no record yet, or still a draft
  const pendingApproval = currentSubs.filter((s) => s.status === "Submitted" || s.status === "Under Review").length;
  const { data: periodAlerts } = useAlerts(currentPeriod);
  const aiAlerts = periodAlerts ?? [];
  const calcsAwaiting = emissions.filter((e) => e.month === currentPeriod && (e.reviewStatus === "Under Review" || e.reviewStatus === "Submitted")).length;
  const { data: rules } = useValidationRules();
  const interval = rules?.inspectionIntervalDays ?? 150;
  const inspectionCutoff = new Date(Date.now() - interval * 86_400_000).toISOString().slice(0, 10);
  const overdueAssets = assets.filter((a) => a.status !== "Shutdown" && a.lastInspection < inspectionCutoff).length;
  const period = reportingPeriods.find((p) => p.period === currentPeriod);
  const activeInitiatives = initiatives.filter((i) => i.status === "In Progress" || i.status === "Planned").length;
  const recentDocs = documents.slice(0, 5);

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Operations"
        title="Operations Workspace"
        description={period ? `Reporting period ${period.period} (${period.status}): submissions due ${period.submissionDue}, approvals due ${period.approvalDue}. Figures below are for this period.` : "No reporting period selected."}
        actions={
          <>
            <Select value={currentPeriod} onValueChange={setPicked}>
              <SelectTrigger className="h-9 w-56" aria-label="Reporting period"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[...reportingPeriods].reverse().map((p) => <SelectItem key={p.id} value={p.period}>{p.period} · {p.status}{p.period === openPeriod ? " (current)" : ""}</SelectItem>)}
              </SelectContent>
            </Select>
            {/* <Button variant="outline" asChild>
              <Link to="/approvals">
                <BadgeCheck className="size-4" /> Review queue
              </Link>
            </Button> */}
            {/* <Button asChild>
              <Link to="/activity">
                <ClipboardList className="size-4" /> New activity submission
              </Link>
            </Button> */}
          </>
        }
      />

      {openPeriod && openPeriod < calendarMonth ? (
        <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          Reporting runs a month behind the calendar: the open reporting period is <span className="font-medium text-foreground">{openPeriod}</span> (today is {calendarMonth}).
          A Sustainability Manager opens the next period in Approvals → Reporting periods once this one is closed. Use the period selector above to view any other period.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Submissions not yet sent" value={due} hint={`Period ${currentPeriod} · ${sent} of ${facilities.length} facilities have submitted (not started or draft count here)`} icon={<ClipboardList className="size-4" />} tone="warning" />
        <StatCard label="Awaiting approval" value={pendingApproval} hint={`Period ${currentPeriod} · submitted, awaiting a reviewer decision`} icon={<BadgeCheck className="size-4" />} tone="info" />
        <StatCard label="Calculations awaiting sign-off" value={calcsAwaiting} hint={`Period ${currentPeriod}`} icon={<Leaf className="size-4" />} tone="default" />
        <StatCard label="Assets overdue for inspection" value={overdueAssets} hint={`Not inspected in ${interval} days (set in Approvals → Validation rules). Asset register only — no workflow yet`} icon={<TriangleAlert className="size-4" />} tone="destructive" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard
          title={`Facility reporting status — ${currentPeriod}`}
          description="Completeness of the current period activity data submission per facility."
          className="lg:col-span-2"
          actions={
            <Button variant="ghost" size="sm" asChild>
              <Link to="/activity">Open module</Link>
            </Button>
          }
        >
          <div className="space-y-4">
            {facilities.map((f) => {
              const sub = currentSubs.find((s) => s.facilityId === f.id);
              return (
                <div key={f.id} className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{f.name}</span>
                      <span className="text-xs text-muted-foreground">{f.region} · {f.units.length} units</span>
                      <StatusBadge value={sub?.status ?? "Draft"} />
                    </div>
                    <Progress value={sub?.completeness ?? 0} className="h-1.5" />
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <span className="tabular text-sm font-semibold text-foreground">{sub?.completeness ?? 0}%</span> complete
                    <br />
                    Owner: {sub?.submittedBy ?? "Unassigned"}
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>

        <SectionCard
          title="AI validation alerts"
          description={`Live, rule-based checks for ${currentPeriod}, outstanding rework/rejections in any open period, and asset inspections; thresholds are set in Approvals → Validation rules. They clear as soon as the issue is resolved.`}
        >
          <ul className="space-y-3">
            {aiAlerts.length === 0 && <li className="text-sm text-muted-foreground">No open alerts for this period.</li>}
            {aiAlerts.map((a) => (
              <li key={a.id} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{a.title}</p>
                  <StatusBadge value={a.severity} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{a.detail}</p>
                <Link className="mt-2 inline-block text-xs font-medium text-primary hover:underline" to={alertLink(a, role)}>
                  {a.action} → {alertLinkLabel(alertLink(a, role))}
                </Link>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard title="Recent activity" description="Audit stream across all modules." className="lg:col-span-2">
          <ol className="relative space-y-4 border-l border-border pl-5">
            {recentActivity.map((r, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[1.4rem] top-1.5 size-2 rounded-full bg-primary" />
                <p className="text-sm">{r.what}</p>
                <p className="text-xs text-muted-foreground">
                  {r.who} · {r.at}
                </p>
              </li>
            ))}
          </ol>
        </SectionCard>

        <div className="space-y-4">
          <SectionCard title="Upcoming reporting deadlines" description="Governance calendar">
            <ul className="space-y-3">
              {reportingPeriods.slice(-3).reverse().map((p) => (
                <li key={p.id} className="flex items-start gap-3">
                  <CalendarClock className="mt-0.5 size-4 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium">Period {p.period}</p>
                      <StatusBadge value={p.status} />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Submission {p.submissionDue} · Approval {p.approvalDue}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard
            title="Recently uploaded evidence"
            description={`${documents.length} documents in repository`}
          >
            <ul className="space-y-2.5">
              {recentDocs.map((d) => (
                <li key={d.id} className="flex items-center gap-2.5">
                  <FileStack className="size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{d.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {facilityName(d.facilityId)} · {d.size} · {d.uploadedBy}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>
        </div>
      </div>

      <SectionCard
        title="Data quality issues requiring action"
        description={`Live issues for ${currentPeriod}: value spikes, zero readings and control-limit breaches in submitted data, plus overdue submissions and approvals. Fixed or approved data drops off automatically.`}
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to={role === "Sustainability Manager" ? "/approvals" : "/activity"}>{role === "Sustainability Manager" ? "Open Approvals" : "Open Activity Data"}</Link>
          </Button>
        }
      >
        <div className="grid gap-3 md:grid-cols-2">
          {aiAlerts.filter((a) => ["anomaly", "due", "approval", "rework", "rejected"].includes(a.kind ?? "")).length === 0 ? (
            <p className="text-sm text-muted-foreground">No data quality issues need action.</p>
          ) : (
            aiAlerts
              .filter((a) => ["anomaly", "due", "approval", "rework", "rejected"].includes(a.kind ?? ""))
              .slice(0, 8)
              .map((a) => (
                <div key={a.id} className="flex gap-3 rounded-lg border border-border p-3">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
                  <div>
                    <p className="text-sm font-medium">{a.title}</p>
                    <p className="text-xs text-muted-foreground">{a.detail}</p>
                  </div>
                </div>
              ))
          )}
        </div>
        {rules ? (
          <p className="mt-3 text-xs text-muted-foreground">
            Rules in force: {rules.spikeEnabled ? `spike ≥ ${rules.spikePct}% (High ≥ ${rules.highPct}%) vs the ${rules.historyMonths}-month mean` : "spike check off"};{" "}
            {rules.zeroEnabled ? "zero reading vs positive history" : "zero check off"};{" "}
            {rules.limits.filter((l) => l.enabled).map((l) => `${l.field} ≤ ${l.max.toLocaleString("en-IN")}`).join(", ") || "no absolute limits"};
            overdue submission/approval vs period deadlines. Rules marked Block stop the submission.
          </p>
        ) : null}
      </SectionCard>

      <p className="text-xs text-muted-foreground">
        Active initiatives: <span className="font-medium text-foreground">{activeInitiatives}</span> reduction projects in
        execution across {new Set(initiatives.filter((i) => i.status === "In Progress" || i.status === "Planned").map((i) => i.facilityId)).size} facilities.
      </p>
    </div>
  );
}
