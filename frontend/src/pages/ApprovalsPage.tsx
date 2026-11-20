import { useMemo, useState } from "react";
import { useOpenNextPeriod, useSetPeriodStatus } from "@/hooks/useApi";
import { BadgeCheck, Clock, History, ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/data-table";
import { Field, PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useStore } from "@/lib/store";
import { type Submission } from "@/types/domain";
import { ValidationRulesPanel } from "@/components/validation-rules-panel";
import { EvidencePanel } from "@/components/evidence-panel";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function ApprovalsPage() {
  usePageMeta("Validation & Approvals — CarbonOps AI", "Reviewer queue for monthly activity submissions with validation results, approval history and workflow SLAs.");
  const { facilities, facilityName, workflows, reportingPeriods } = useStore();
  const openNext = useOpenNextPeriod();
  const setPeriodStatus = useSetPeriodStatus();
  const periodAction = async (fn: () => Promise<{ period: string; status: string }>, ok: string) => {
    try {
      const p = await fn();
      toast.success(`Period ${p.period} → ${p.status}`, { description: ok });
    } catch (error) {
      toast.error("Period change not allowed", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const { submissions, setSubmissionStatus, audit } = useStore();
  const [detail, setDetail] = useState<Submission | null>(null);
  const [comment, setComment] = useState("");
  const [facility, setFacility] = useState("all");

  const queue = useMemo(
    () =>
      submissions.filter(
        (s) => ["Submitted", "Under Review"].includes(s.status) && (facility === "all" || s.facilityId === facility),
      ),
    [submissions, facility],
  );
  const decided = useMemo(
    () => submissions.filter((s) => ["Approved", "Rejected"].includes(s.status) && (facility === "all" || s.facilityId === facility)),
    [submissions, facility],
  );

  const act = async (s: Submission, status: "Approved" | "Rejected" | "Under Review") => {
    if (status === "Rejected" && !comment.trim()) {
      toast.error("Comment required", { description: "Provide a reason before rejecting a submission." });
      return;
    }
    try {
      await setSubmissionStatus(s.id, status, comment.trim(), s.revision);
      toast.success(`${s.id} → ${status}`, { description: comment.trim() || "Decision recorded in the audit trail." });
      setComment("");
      setDetail(null);
    } catch (error) {
      toast.error("Decision could not be recorded", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const columns: Column<Submission>[] = [
    { key: "id", header: "Submission", sortable: true, value: (s) => s.id, render: (s) => <span className="font-medium">{s.id}</span> },
    { key: "facility", header: "Facility", sortable: true, value: (s) => facilityName(s.facilityId), render: (s) => (
      <div><p>{facilityName(s.facilityId)}</p><p className="text-xs text-muted-foreground">{s.unit}</p></div>
    ) },
    { key: "month", header: "Period", sortable: true, value: (s) => s.month },
    { key: "by", header: "Submitted by", sortable: true, value: (s) => s.submittedBy },
    { key: "completeness", header: "Completeness", align: "right", sortable: true, value: (s) => s.completeness, render: (s) => <span className="tabular">{s.completeness}%</span> },
    { key: "validation", header: "Validation", sortable: true, value: (s) => s.validation, render: (s) => <StatusBadge value={s.validation} /> },
    { key: "flags", header: "Anomalies", align: "right", value: (s) => s.anomalies.length, render: (s) => <span className="tabular">{s.anomalies.length}</span> },
    { key: "status", header: "Status", sortable: true, value: (s) => s.status, render: (s) => <StatusBadge value={s.status} /> },
    { key: "updated", header: "Last updated", sortable: true, value: (s) => s.updatedAt },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Governance"
        title="Validation & Approvals"
        description="Reviewer workspace for monthly submissions. Decisions here release data into the carbon accounting ledger."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Pending review" value={queue.length} hint="Awaiting reviewer decision" icon={<Clock className="size-4" />} tone="warning" />
        <StatCard label="Approved" value={submissions.filter((s) => s.status === "Approved").length} hint="Released to carbon ledger" icon={<BadgeCheck className="size-4" />} tone="success" />
        <StatCard label="Rejected" value={submissions.filter((s) => s.status === "Rejected").length} hint="Returned for rework" icon={<ThumbsDown className="size-4" />} tone="destructive" />
        <StatCard label="Audit entries" value={audit.length} hint="Recorded governance actions" icon={<History className="size-4" />} />
      </div>

      <Tabs defaultValue="queue">
        <TabsList>
          <TabsTrigger value="queue">Approval queue</TabsTrigger>
          <TabsTrigger value="history">Decision history</TabsTrigger>
          <TabsTrigger value="periods">Reporting periods</TabsTrigger>
          <TabsTrigger value="rules">Validation rules</TabsTrigger>
          <TabsTrigger value="workflows">Workflow configuration</TabsTrigger>
          <TabsTrigger value="audit">Audit trail</TabsTrigger>
        </TabsList>

        <TabsContent value="queue" className="pt-4">
          <DataTable
            data={queue}
            columns={columns}
            rowKey={(s) => s.id}
            onRowClick={setDetail}
            pageSize={8}
            emptyTitle="Approval queue is clear"
            emptyHint="No submissions are currently awaiting review for this selection."
            searchKeys={(s) => `${s.id} ${facilityName(s.facilityId)} ${s.submittedBy} ${s.month}`}
            searchPlaceholder="Search submissions awaiting review…"
            toolbar={
              <Select value={facility} onValueChange={setFacility}>
                <SelectTrigger className="h-9 w-52"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All facilities</SelectItem>
                  {facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}
                </SelectContent>
              </Select>
            }
            actions={(s) => (
              <div className="flex justify-end gap-1.5">
                <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setDetail(s); }}>Review</Button>
              </div>
            )}
          />
        </TabsContent>

        <TabsContent value="history" className="pt-4">
          <DataTable
            data={decided}
            columns={columns}
            rowKey={(s) => s.id}
            onRowClick={setDetail}
            pageSize={8}
            searchKeys={(s) => `${s.id} ${facilityName(s.facilityId)} ${s.reviewer} ${s.status}`}
            searchPlaceholder="Search decided submissions…"
          />
        </TabsContent>

        <TabsContent value="periods" className="pt-4">
          <SectionCard
            title="Reporting periods"
            description="Data entry is only possible in Open and In Review periods. A period can be locked once every submission in it is approved; locking is final."
            actions={
              <Button size="sm" disabled={openNext.isPending} onClick={() => periodAction(() => openNext.mutateAsync(undefined), "Previous open period moved to review.")}>
                Open next period
              </Button>
            }
          >
            <ul className="divide-y divide-border">
              {[...reportingPeriods].reverse().map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <p className="text-sm font-medium">Period {p.period} <StatusBadge value={p.status} /></p>
                    <p className="text-xs text-muted-foreground">
                      Submission due {p.submissionDue} · Approval due {p.approvalDue}{p.lockedOn !== "—" ? ` · Locked ${p.lockedOn}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {p.status === "Open" && (
                      <Button size="sm" variant="outline" onClick={() => periodAction(() => setPeriodStatus.mutateAsync({ period: p.period, status: "In Review" }), "No new period opened.")}>
                        Move to review
                      </Button>
                    )}
                    {p.status !== "Locked" && (
                      <Button size="sm" variant="outline" onClick={() => periodAction(() => setPeriodStatus.mutateAsync({ period: p.period, status: "Locked" }), "Data in this period is now final.")}>
                        Lock period
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>
        </TabsContent>

        <TabsContent value="rules" className="pt-4">
          <ValidationRulesPanel />
        </TabsContent>

        <TabsContent value="workflows" className="pt-4">
          <SectionCard title="Approval workflows" description="Configured routing, SLA and escalation paths">
            <ul className="divide-y divide-border">
              {workflows.map((w) => (
                <li key={w.id} className="space-y-1 py-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium">{w.name}</p>
                    <StatusBadge value={w.status} />
                  </div>
                  <p className="text-xs text-muted-foreground">{w.steps}</p>
                  <p className="text-xs text-muted-foreground">SLA {w.sla} · Escalation: {w.escalation}</p>
                </li>
              ))}
            </ul>
          </SectionCard>
        </TabsContent>

        <TabsContent value="audit" className="pt-4">
          <SectionCard title="Audit trail" description="Immutable log of governance actions in this session">
            <ul className="divide-y divide-border">
              {audit.map((a) => (
                <li key={a.id} className="flex items-start justify-between gap-4 py-3">
                  <div>
                    <p className="text-sm"><span className="font-medium">{a.who}</span> — {a.action} <span className="text-muted-foreground">{a.target}</span></p>
                    <p className="text-xs text-muted-foreground">{a.detail}</p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">{a.at}</span>
                </li>
              ))}
            </ul>
          </SectionCard>
        </TabsContent>
      </Tabs>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>{detail.id}</SheetTitle>
                <SheetDescription>{facilityName(detail.facilityId)} · {detail.unit} · {detail.month}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Status" value={<StatusBadge value={detail.status} />} />
                  <Field label="Validation" value={<StatusBadge value={detail.validation} />} />
                  <Field label="Submitted by" value={detail.submittedBy} />
                  <Field label="Reviewer" value={detail.reviewer} />
                  <Field label="Completeness" value={`${detail.completeness}%`} />
                  <Field label="Last updated" value={detail.updatedAt} />
                </div>

                <SectionCard title="Key reported quantities" description="Basis for the carbon calculation">
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div><dt className="text-xs text-muted-foreground">Electricity</dt><dd className="tabular">{detail.data.electricity.toLocaleString("en-IN")} kWh</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Diesel</dt><dd className="tabular">{detail.data.diesel.toLocaleString("en-IN")} L</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Natural gas</dt><dd className="tabular">{detail.data.naturalGas.toLocaleString("en-IN")} SCM</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Flare gas</dt><dd className="tabular">{detail.data.flareGas.toLocaleString("en-IN")} SCM</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Methane leakage</dt><dd className="tabular">{detail.data.methaneLeak.toLocaleString("en-IN")} kg</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Production</dt><dd className="tabular">{detail.data.productionVolume.toLocaleString("en-IN")} boe</dd></div>
                  </dl>
                </SectionCard>

                {detail.anomalies.length ? (
                  <SectionCard title="Validation findings" description="Automated checks requiring reviewer judgement">
                    <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
                      {detail.anomalies.map((a) => <li key={a}>{a}</li>)}
                    </ul>
                  </SectionCard>
                ) : null}

                <EvidencePanel facilityId={detail.facilityId} month={detail.month} canUpload={false} />

                {["Approved", "Rejected"].includes(detail.status) ? (
                  <SectionCard title="Decision recorded" description="Decided submissions are read-only">
                    <p className="text-sm text-muted-foreground">
                      {detail.status === "Approved"
                        ? "Approved submissions are final."
                        : "Rejected — the data owner must correct and resubmit it; it then returns to the approval queue."}
                      {detail.reviewerComments ? ` Reviewer note: ${detail.reviewerComments}` : ""}
                    </p>
                  </SectionCard>
                ) : ["Submitted", "Under Review"].includes(detail.status) ? (
                <SectionCard title="Reviewer decision" description="Comments are stored in the audit trail">
                  <Textarea rows={3} placeholder="Reason for approval, rejection or clarification request…" value={comment} onChange={(e) => setComment(e.target.value)} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => act(detail, "Approved")}><ThumbsUp className="size-4" /> Approve</Button>
                    <Button size="sm" variant="outline" onClick={() => act(detail, "Rejected")}><ThumbsDown className="size-4" /> Reject</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(detail, "Under Review")}>Request clarification</Button>
                  </div>
                </SectionCard>
                ) : null}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
