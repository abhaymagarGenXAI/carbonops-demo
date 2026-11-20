import { useMemo, useState } from "react";
import { BASIS_LABEL, countsToward, type Basis } from "@/lib/emissions";
import { Calculator, CheckCircle2, Download, MessageSquare, RefreshCw, TrendingDown } from "lucide-react";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InventoryExportDialog } from "@/components/inventory-export-dialog";
import { Scope3Panel } from "@/components/scope3-panel";
import { FactorAdmin } from "@/components/factor-admin";
import { TargetsPanel } from "@/components/targets-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/data-table";
import { Field, PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useStore } from "@/lib/store";
import { useRecalculateEmissions } from "@/hooks/useApi";
import { type EmissionRecord, type RecalculateResult } from "@/types/domain";
import { usePageMeta } from "@/hooks/use-page-meta";

const SCOPE_COLORS: Record<string, string> = {
  "Scope 1": "var(--chart-1)",
  "Scope 2": "var(--chart-2)",
  "Scope 3": "var(--chart-3)",
};

export default function CarbonPage() {
  usePageMeta("Carbon Accounting — CarbonOps AI", "Scope 1, 2 and 3 emissions calculated from approved activity data, with factor traceability, variance analysis and reviewer sign-off.");
  const { currentPeriod, facilities, facilityName, months } = useStore();

  const { emissions, setEmissionReview } = useStore();
  const recalc = useRecalculateEmissions();
  const [facility, setFacility] = useState("all");
  const [scope, setScope] = useState("all");
  // One period filter for the whole page (KPIs, overview, ledger, recalculation scope). "all" = every period combined.
  const [month, setMonth] = useState(currentPeriod);
  const [basis, setBasis] = useState<Basis>("approved");
  const [exportOpen, setExportOpen] = useState(false);
  const isAll = month === "all";
  const overviewMonth = isAll ? (months[months.length - 1] ?? currentPeriod) : month;
  const periodLabel = isAll ? "all periods" : month;
  const prevMonth = isAll ? null : months[months.indexOf(overviewMonth) - 1] ?? null;
  const [reviewFilter, setReviewFilter] = useState("active");
  const [detail, setDetail] = useState<EmissionRecord | null>(null);
  const [comment, setComment] = useState("");
  const [recalcOpen, setRecalcOpen] = useState(false);
  const [preview, setPreview] = useState<RecalculateResult | null>(null);

  const recalcScope = { month: month === "all" ? undefined : month, facilityId: facility === "all" ? undefined : facility };
  const recalcLabel = `${recalcScope.facilityId ? facilityName(recalcScope.facilityId) : "All facilities"} · ${recalcScope.month ?? "all periods"}`;
  const changeCount = preview ? preview.created + preview.updated + preview.traceLinked : 0;

  const runRecalc = async (dryRun: boolean) => {
    try {
      const result = await recalc.mutateAsync({ ...recalcScope, dryRun });
      if (dryRun) {
        setPreview(result);
      } else {
        toast.success("Emissions recalculated", { description: `${result.updated} updated, ${result.created} created, ${result.traceLinked} linked to factor versions.` });
        setPreview(null);
        setRecalcOpen(false);
      }
    } catch (error) {
      toast.error(dryRun ? "Preview failed" : "Recalculation failed", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const scoped = useMemo(() => emissions.filter((e) => facility === "all" || e.facilityId === facility), [emissions, facility]);
  // Totals and charts only use records that count toward the chosen basis; rejected/draft records never do.
  const counted = useMemo(() => scoped.filter((e) => countsToward(e.reviewStatus, basis)), [scoped, basis]);
  const rows = useMemo(
    () =>
      scoped.filter(
        (e) =>
          (scope === "all" || e.scope === scope) &&
          (month === "all" || e.month === month) &&
          (reviewFilter === "all" || (reviewFilter === "active" ? e.reviewStatus !== "Rejected" && e.reviewStatus !== "Draft" : e.reviewStatus === reviewFilter)),
      ),
    [scoped, scope, month, reviewFilter],
  );

  const totals = useMemo(() => {
    const set = counted.filter((e) => isAll || e.month === overviewMonth);
    const by = (s: string) => set.filter((e) => e.scope === s).reduce((a, b) => a + b.co2e, 0);
    const total = set.reduce((a, b) => a + b.co2e, 0);
    const prev = set.reduce((a, b) => a + b.prevCo2e, 0);
    return { s1: by("Scope 1"), s2: by("Scope 2"), s3: by("Scope 3"), total, delta: prev ? ((total - prev) / prev) * 100 : 0 };
  }, [counted, overviewMonth, isAll]);

  const trend = useMemo(
    () =>
      months.filter((m) => m <= overviewMonth).slice(-6).map((m) => {
        const set = counted.filter((e) => e.month === m);
        return {
          month: m.slice(5),
          "Scope 1": Math.round(set.filter((e) => e.scope === "Scope 1").reduce((a, b) => a + b.co2e, 0)),
          "Scope 2": Math.round(set.filter((e) => e.scope === "Scope 2").reduce((a, b) => a + b.co2e, 0)),
        };
      }),
    [counted, months, overviewMonth],
  );

  const bySource = useMemo(() => {
    const set = counted.filter((e) => isAll || e.month === overviewMonth);
    const map = new Map<string, number>();
    set.forEach((e) => map.set(e.source, (map.get(e.source) ?? 0) + e.co2e));
    return [...map.entries()].map(([name, value]) => ({ name, value: Math.round(value) }));
  }, [counted, overviewMonth, isAll]);

  const pending = scoped.filter((e) => e.reviewStatus === "Under Review" && (isAll || e.month === overviewMonth)).length;

  const columns: Column<EmissionRecord>[] = [
    { key: "id", header: "Calculation ID", sortable: true, value: (e) => e.id, render: (e) => <span className="font-medium">{e.id}</span> },
    { key: "facility", header: "Facility", sortable: true, value: (e) => facilityName(e.facilityId) },
    { key: "source", header: "Emission source", sortable: true, value: (e) => e.source },
    { key: "scope", header: "Scope", sortable: true, value: (e) => e.scope },
    { key: "activity", header: "Activity value", align: "right", sortable: true, value: (e) => e.activityValue, render: (e) => (
      <span className="tabular">{e.activityValue.toLocaleString("en-IN")} <span className="text-muted-foreground">{e.unit}</span></span>
    ) },
    { key: "factor", header: "Factor applied", align: "right", value: (e) => e.factor, render: (e) => (
      <span className="tabular">{e.factor} <span className="text-muted-foreground">{e.factorUnit}</span></span>
    ) },
    { key: "co2e", header: "tCO₂e", align: "right", sortable: true, value: (e) => e.co2e, render: (e) => <span className="tabular font-medium">{e.co2e.toLocaleString("en-IN")}</span> },
    { key: "delta", header: "vs prior", align: "right", sortable: true, value: (e) => e.co2e - e.prevCo2e, render: (e) => {
      const d = e.prevCo2e ? ((e.co2e - e.prevCo2e) / e.prevCo2e) * 100 : 0;
      return <span className={d > 5 ? "tabular text-destructive" : d < -5 ? "tabular text-success" : "tabular"}>{d > 0 ? "+" : ""}{d.toFixed(1)}%</span>;
    } },
    { key: "calc", header: "Calculation", value: (e) => e.calcStatus, render: (e) => <StatusBadge value={e.calcStatus} /> },
    { key: "review", header: "Review", sortable: true, value: (e) => e.reviewStatus, render: (e) => <StatusBadge value={e.reviewStatus} /> },
  ];

  const review = async (status: "Approved" | "Rejected" | "Under Review") => {
    if (!detail) return;
    if (status !== "Approved" && !comment.trim()) {
      toast.error("Comment required", { description: "Tell the data owner what needs to be corrected." });
      return;
    }
    try {
      await setEmissionReview(detail.id, status, comment.trim());
      toast.success(status === "Under Review" ? `Rework requested for ${detail.id}` : `${detail.id} ${status.toLowerCase()}`, { description: comment.trim() || "No reviewer comment provided." });
      setComment("");
      setDetail(null);
    } catch (error) {
      toast.error("Review could not be recorded", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Carbon"
        title="Carbon Accounting"
        description="GHG Protocol aligned emissions ledger. Every figure traces to an activity record, an emission factor version and a reviewer decision."
        actions={
          <>
            <Button variant="outline" onClick={() => { setPreview(null); setRecalcOpen(true); }}>
              <RefreshCw className="size-4" /> Recalculate period
            </Button>
            <Button variant="outline" onClick={() => setExportOpen(true)}>
              <Download className="size-4" /> Export inventory
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total emissions" value={`${Math.round(totals.total).toLocaleString("en-IN")} tCO₂e`} hint={basis === "approved" ? `Period ${periodLabel} · approved records only${totals.total === 0 ? " (none approved yet)" : ""}` : `Period ${periodLabel} · incl. pending review`} icon={<Calculator className="size-4" />} />
        <StatCard label="Scope 1" value={`${Math.round(totals.s1).toLocaleString("en-IN")} tCO₂e`} hint="Combustion, flaring, fugitives" icon={<TrendingDown className="size-4" />} tone="warning" />
        <StatCard label="Scope 2" value={`${Math.round(totals.s2).toLocaleString("en-IN")} tCO₂e`} hint="Purchased electricity & steam" icon={<TrendingDown className="size-4" />} tone="info" />
        <StatCard label="Awaiting review" value={pending} hint="Calculations pending sign-off" icon={<CheckCircle2 className="size-4" />} tone={pending ? "warning" : "success"} />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>Charts and totals count:</span>
        <Select value={basis} onValueChange={(v) => setBasis(v as Basis)}>
          <SelectTrigger className="h-8 w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            {(Object.keys(BASIS_LABEL) as Basis[]).map((b) => <SelectItem key={b} value={b}>{BASIS_LABEL[b]}</SelectItem>)}
          </SelectContent>
        </Select>
        <span>Reporting period:</span>
        <Select value={month} onValueChange={setMonth}>
          <SelectTrigger className="h-8 w-40" aria-label="Reporting period"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All periods</SelectItem>
            {[...months].reverse().map((m) => <SelectItem key={m} value={m}>{m}{m === currentPeriod ? " (open)" : ""}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={facility} onValueChange={setFacility}>
          <SelectTrigger className="h-8 w-48" aria-label="Facility"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All facilities</SelectItem>
            {facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <span>Applies to the KPIs, overview and ledger. Rejected and draft records are never counted.</span>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ledger">Calculation ledger</TabsTrigger>
          <TabsTrigger value="targets">Targets &amp; baseline</TabsTrigger>
          <TabsTrigger value="scope3">Scope 3</TabsTrigger>
          <TabsTrigger value="factors">Emission factors</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 pt-4">
          <div className="grid gap-4 lg:grid-cols-5">
            <SectionCard className="lg:col-span-3" title="Emissions trend by scope" description={`tCO₂e per reporting month, up to ${overviewMonth} (${basis === "approved" ? "approved records" : "approved + pending"})`}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend} margin={{ left: 8, bottom: 18 }}>
                    <defs>
                      <linearGradient id="s1" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.45} />
                        <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="s2" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--chart-2)" stopOpacity={0.45} />
                        <stop offset="95%" stopColor="var(--chart-2)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="month" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Reporting month", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Emissions (tCO₂e)", angle: -90, position: "insideLeft", fontSize: 12, fill: "var(--muted-foreground)", style: { textAnchor: "middle" } }} />
                    <RTooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${Number(v).toLocaleString("en-IN")} tCO₂e`, n]} labelFormatter={(l) => `Month ${l}`} />
                    <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="Scope 1" stroke="var(--chart-1)" fill="url(#s1)" strokeWidth={2} />
                    <Area type="monotone" dataKey="Scope 2" stroke="var(--chart-2)" fill="url(#s2)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>

            <SectionCard className="lg:col-span-2" title="Contribution by source" description={`Reporting period: ${periodLabel} · tCO₂e by source`}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={bySource} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                      {bySource.map((_, i) => (
                        <Cell key={i} fill={`var(--chart-${(i % 5) + 1})`} />
                      ))}
                    </Pie>
                    <RTooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${Number(v).toLocaleString("en-IN")} tCO₂e`, n]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          </div>

          <SectionCard title={`Period movement — ${periodLabel}`} description={isAll ? "All periods are combined, so there is no single earlier period to compare with" : prevMonth ? `${overviewMonth} compared with ${prevMonth}` : `${overviewMonth} is the first reporting period`}>
            <p className="text-sm text-muted-foreground">
              {totals.total === 0 ? (
                <>No {basis === "approved" ? "approved " : ""}emissions recorded for {periodLabel} yet. Switch the basis to include records pending review, or approve the period's submissions in Approvals.</>
              ) : (
                <>
                  In {periodLabel}, total emissions{" "}
                  {prevMonth ? (
                    <>
                      moved{" "}
                      <span className={totals.delta > 0 ? "font-medium text-destructive" : "font-medium text-success"}>
                        {totals.delta > 0 ? "+" : ""}{totals.delta.toFixed(1)}%
                      </span>{" "}
                      compared with {prevMonth}
                    </>
                  ) : "have no earlier period to compare with"}
                  . Scope 1 accounts for {((totals.s1 / totals.total) * 100).toFixed(0)}% of the {periodLabel} inventory
                  {bySource.length ? `, led by ${[...bySource].sort((a, b) => b.value - a.value)[0]!.name}` : ""}. Scope 2 uses the grid factor version effective for the period (see the Emission factors tab).
                </>
              )}
            </p>
          </SectionCard>
        </TabsContent>

        <TabsContent value="ledger" className="pt-4">
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(e) => e.id}
            pageSize={10}
            onRowClick={setDetail}
            searchKeys={(e) => `${e.id} ${facilityName(e.facilityId)} ${e.source} ${e.scope} ${e.factorRef}`}
            searchPlaceholder="Search calculation, source or factor reference…"
            toolbar={
              <>
                <Select value={scope} onValueChange={setScope}>
                  <SelectTrigger className="h-9 w-36"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All scopes</SelectItem>
                    {Object.keys(SCOPE_COLORS).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={reviewFilter} onValueChange={setReviewFilter}>
                  <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active (excl. rejected)</SelectItem>
                    <SelectItem value="all">All incl. rejected</SelectItem>
                    <SelectItem value="Under Review">Under review</SelectItem>
                    <SelectItem value="Approved">Approved</SelectItem>
                    <SelectItem value="Rejected">Rejected</SelectItem>
                  </SelectContent>
                </Select>
              </>
            }
          />
        </TabsContent>

        <TabsContent value="targets" className="pt-4">
          <TargetsPanel />
        </TabsContent>

        <TabsContent value="scope3" className="pt-4">
          <Scope3Panel />
        </TabsContent>

        <TabsContent value="factors" className="pt-4">
          <FactorAdmin />
        </TabsContent>
      </Tabs>

      <Dialog open={recalcOpen} onOpenChange={(o) => { setRecalcOpen(o); if (!o) setPreview(null); }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Recalculate emissions</DialogTitle>
            <DialogDescription>
              Use after an emission factor is added or corrected, or after legacy records were created: it re-runs the calculation for every record in scope from the stored activity data and the factor version effective for its month. It does not change the status of anything whose figure is unchanged. Scope: {recalcLabel}. Locked periods are never changed;
              approved records whose figure changes return to review.
            </DialogDescription>
          </DialogHeader>
          {preview ? (
            <div className="space-y-3 text-sm">
              <p className="tabular">
                {preview.evaluated} submission(s) checked · <b>{preview.updated}</b> to update · <b>{preview.created}</b> to create ·{" "}
                <b>{preview.traceLinked}</b> to link to a factor version · {preview.unchanged} unchanged
              </p>
              {preview.items.length > 0 && (
                <div className="max-h-56 overflow-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 text-left"><tr><th className="p-2">Record</th><th className="p-2">Source</th><th className="p-2 text-right">tCO₂e</th><th className="p-2">Reason</th></tr></thead>
                    <tbody>
                      {preview.items.map((i) => (
                        <tr key={i.id} className="border-t">
                          <td className="p-2">{i.id}</td><td className="p-2">{i.source}</td>
                          <td className="tabular p-2 text-right">{i.oldCo2e ?? "—"} → {i.newCo2e}</td><td className="p-2 text-muted-foreground">{i.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {preview.skipped.length > 0 && (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {preview.skipped.map((k, idx) => <li key={idx}>Skipped {k.target}: {k.reason}</li>)}
                </ul>
              )}
              {changeCount === 0 && <p className="text-muted-foreground">Nothing to change — the ledger already matches the active factors and activity data.</p>}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Preview first: nothing is written until you apply.</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => runRecalc(true)} disabled={recalc.isPending}>Preview changes</Button>
            <Button onClick={() => runRecalc(false)} disabled={recalc.isPending || !preview || changeCount === 0}>Apply {changeCount ? `${changeCount} change(s)` : ""}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>{detail.source}</SheetTitle>
                <SheetDescription>{facilityName(detail.facilityId)} · {detail.month} · {detail.id}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Scope" value={detail.scope} />
                  <Field label="Calculation status" value={<StatusBadge value={detail.calcStatus} />} />
                  <Field label="Activity value" value={`${detail.activityValue.toLocaleString("en-IN")} ${detail.unit}`} />
                  <Field label="Emission factor" value={`${detail.factor} ${detail.factorUnit}`} />
                  <Field label="Factor reference" value={detail.factorRef} />
                  <Field label="Review status" value={<StatusBadge value={detail.reviewStatus} />} />
                  <Field label="Factor version" value={detail.factorId ?? "Legacy record — run a recalculation to link"} />
                  <Field label="Source submission" value={detail.submissionId ?? "—"} />
                </div>

                <SectionCard title="Calculation breakdown" description="Formula applied to this record">
                  <p className="tabular text-sm">
                    {detail.activityValue.toLocaleString("en-IN")} {detail.unit} × {detail.factor} {detail.factorUnit} ÷ 1000 ={" "}
                    <span className="font-semibold">{detail.co2e.toLocaleString("en-IN")} tCO₂e</span>
                  </p>
                  {detail.calcNote ? <p className="mt-2 text-xs text-warning">{detail.calcNote}</p> : null}
                  {detail.calculatedAt ? <p className="mt-2 text-xs text-muted-foreground">Calculated {detail.calculatedAt}</p> : null}
                  <p className="mt-2 text-xs text-muted-foreground">Previous period: {detail.prevCo2e.toLocaleString("en-IN")} tCO₂e</p>
                </SectionCard>

                <SectionCard title="Review comments" description={`${detail.comments.length} comment(s)`}>
                  {detail.comments.length ? (
                    <ul className="space-y-3">
                      {detail.comments.map((c, i) => (
                        <li key={i} className="rounded-md bg-muted/50 p-3">
                          <p className="text-xs font-medium">{c.by} <span className="font-normal text-muted-foreground">· {c.at}</span></p>
                          <p className="mt-1 text-sm text-muted-foreground">{c.text}</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No comments recorded yet.</p>
                  )}
                  <Textarea
                    className="mt-3"
                    rows={3}
                    placeholder="Add a reviewer comment before approving or rejecting…"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                  {!detail.submissionId ? (
                    <div className="mt-3 flex gap-2">
                      <Button size="sm" onClick={() => review("Approved")}><CheckCircle2 className="size-4" /> Approve calculation</Button>
                      <Button size="sm" variant="outline" onClick={() => review("Rejected")}><MessageSquare className="size-4" /> Reject & request rework</Button>
                    </div>
                  ) : detail.reviewStatus === "Under Review" ? (
                    <>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" onClick={() => review("Under Review")}><MessageSquare className="size-4" /> Request rework</Button>
                        <Button size="sm" variant="outline" onClick={() => review("Rejected")}>Reject submission</Button>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        A calculation is a view of its submission {detail.submissionId}. Rework or rejection is sent to the data owner as an alert on that submission;
                        approve it as a whole in Approvals.
                      </p>
                    </>
                  ) : (
                    <p className="mt-3 text-xs text-muted-foreground">
                      Read-only: this calculation follows submission {detail.submissionId} ({detail.reviewStatus.toLowerCase()}). Decisions are made on the submission in Approvals while it is awaiting review.
                    </p>
                  )}
                </SectionCard>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
      <InventoryExportDialog open={exportOpen} onOpenChange={setExportOpen} />
    </div>
  );
}
