import { BASIS_LABEL, countsToward, type Basis } from "@/lib/emissions";
import { useMemo, useState } from "react";
import { AlertTriangle, Download, Gauge, RefreshCw, Sparkles, Zap } from "lucide-react";
import { toast } from "sonner";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/data-table";
import { Field, PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { type EnergyReconcileResult, type EnergyRecord } from "@/types/domain";
import { downloadCsv, toCsv } from "@/lib/csv";
import { useReconcileEnergy, useUpdateEnergyRecord, useValidationRules } from "@/hooks/useApi";
import { usePageMeta } from "@/hooks/use-page-meta";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";

const fmt = (n: number) => n.toLocaleString("en-IN");

const STREAM_UNIT: Record<string, string> = { Electricity: "kWh", "Natural gas": "SCM", Diesel: "L", Steam: "t", Renewable: "kWh" };

/** One approval-basis rule for the KPIs, charts and consumption records. Records not yet linked to a submission (legacy) count as
 *  approved unless their validation is still "Pending"; run "Reconcile" to link them. */
const inBasis = (r: EnergyRecord, basis: Basis) =>
  r.submissionStatus ? countsToward(r.submissionStatus, basis) : r.validation === "Pending" ? basis === "pending" : true;

export default function EnergyPage() {
  usePageMeta("Energy Management — CarbonOps AI", "Track electricity, fuel, steam and renewable consumption by facility with meter references, cost and anomaly detection.");
  const { energyRecords, allFacilities, facilityName, months, role, currentPeriod } = useStore();
  const { can } = useAuth();
  const updateEnergy = useUpdateEnergyRecord();
  const reconcile = useReconcileEnergy();
  const { data: rules } = useValidationRules();
  const canEdit = can("energy.edit"); // same permission the API checks
  const canReconcile = can("energy.reconcile");
  const [edit, setEdit] = useState({ meterRef: "", invoiceRef: "", cost: "" });
  const [reconcileOpen, setReconcileOpen] = useState(false);
  const [preview, setPreview] = useState<EnergyReconcileResult | null>(null);

  const [facility, setFacility] = useState("all");
  const [stream, setStream] = useState("all");
  // One period filter for the KPIs, charts-highlight and the records tab. "all" = every period combined.
  const [from, setFrom] = useState(""); // "" = open-ended: earliest / latest period
  const [to, setTo] = useState("");
  const [detail, setDetail] = useState<EnergyRecord | null>(null);
  const [basis, setBasis] = useState<Basis>("approved");
  const [tab, setTab] = useState("analytics");
  const inRange = (m: string) => (!from || m >= from) && (!to || m <= to);
  const rangeBad = !!from && !!to && from > to;
  const periodLabel = !from && !to ? "all periods" : from === to ? from : `${from || "earliest"} → ${to || "latest"}`;
  const reconcileScope = {
    month: from && from === to ? from : undefined,
    facilityId: facility === "all" ? undefined : facility,
  };

  const rows = useMemo(
    () =>
      energyRecords.filter(
        (r) =>
          (facility === "all" || r.facilityId === facility) &&
          (stream === "all" || r.stream === stream) &&
          inRange(r.month) &&
          inBasis(r, basis), // same approval basis as the KPIs and charts
      ),
    [energyRecords, facility, stream, from, to, basis],
  );

  // Analytics count approved data by default; "pending" adds submitted data awaiting review. Legacy unlinked records always count.
  const scoped = useMemo(
    () => energyRecords.filter((r) => (facility === "all" || r.facilityId === facility) && inBasis(r, basis)),
    [energyRecords, facility, basis],
  );

  // Analytics honour the stream filter (the renewable share needs electricity + renewable, so it ignores it).
  const streamScoped = useMemo(() => scoped.filter((r) => stream === "all" || r.stream === stream), [scoped, stream]);

  const trend = useMemo(
    () =>
      months.filter(inRange).map((m) => {
        const set = streamScoped.filter((r) => r.month === m);
        const steam = set.filter((r) => r.stream === "Steam").reduce((a, b) => a + b.quantity, 0);
        const kwh = set.filter((r) => r.stream === "Electricity").reduce((a, b) => a + b.quantity, 0);
        const diesel = set.filter((r) => r.stream === "Diesel").reduce((a, b) => a + b.quantity, 0);
        const gas = set.filter((r) => r.stream === "Natural Gas").reduce((a, b) => a + b.quantity, 0);
        const renewable = set.filter((r) => r.stream === "Renewable Energy").reduce((a, b) => a + b.quantity, 0);
        const gj = set.reduce((a, b) => a + (b.energyGj ?? 0), 0); // computed server-side from stored quantities
        return {
          month: m.slice(5),
          Electricity: Math.round(kwh / 1000),
          Diesel: Math.round(diesel / 1000),
          "Natural gas": Math.round(gas / 1000),
          Renewable: Math.round(renewable / 1000),
          Steam: Math.round(steam / 1000),
          intensity: +(gj / 1000).toFixed(1),
        };
      }),
    [streamScoped, months, from, to],
  );

  const current = scoped.filter((r) => inRange(r.month));
  const totalCost = current.filter((r) => stream === "all" || r.stream === stream).reduce((a, b) => a + b.cost, 0);
  const renewableShare = (() => {
    const ren = current.filter((r) => r.stream === "Renewable Energy").reduce((a, b) => a + b.quantity, 0);
    const ele = current.filter((r) => r.stream === "Electricity").reduce((a, b) => a + b.quantity, 0);
    return ele ? ((ren / (ele + ren)) * 100).toFixed(1) : "0";
  })();
  const anomalies = streamScoped.filter((r) => inRange(r.month) && (r.validation === "Anomaly" || r.validation === "Missing"));
  const energyTj = current.filter((r) => stream === "all" || r.stream === stream).reduce((a, b) => a + (b.energyGj ?? 0), 0) / 1000;

  const exportCsv = () => {
    const csv = toCsv(
      ["Record", "Facility", "Month", "Stream", "Quantity", "Unit", "Energy (GJ)", "MoM variance %", "Cost (INR)", "Meter ref", "Invoice ref", "Validation", "Source submission"],
      rows.map((r) => [r.id, facilityName(r.facilityId), r.month, r.stream, r.quantity, r.unit, r.energyGj ?? "", r.variance, r.cost, r.meterRef, r.invoiceRef, r.validation, r.submissionId ?? ""]),
    );
    downloadCsv(`energy-records-${facility === "all" ? "all-facilities" : facility}-${from}_${to}.csv`, csv);
    toast.success("Energy dataset exported", { description: `${rows.length} records downloaded as CSV.` });
  };

  const openDetail = (r: EnergyRecord | null) => {
    setDetail(r);
    if (r) setEdit({ meterRef: r.meterRef, invoiceRef: r.invoiceRef, cost: String(r.cost) });
  };

  const saveEdit = async () => {
    if (!detail) return;
    const cost = Number(edit.cost);
    if (!Number.isFinite(cost) || cost < 0) {
      toast.error("Invalid cost", { description: "Cost must be a number ≥ 0." });
      return;
    }
    try {
      const updated = await updateEnergy.mutateAsync({ id: detail.id, changes: { meterRef: edit.meterRef.trim(), invoiceRef: edit.invoiceRef.trim(), cost } });
      setDetail(updated);
      toast.success(`${updated.id} updated`, { description: "Meter, invoice and cost saved." });
    } catch (error) {
      toast.error("Could not save", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const runReconcile = async (dryRun: boolean) => {
    try {
      const result = await reconcile.mutateAsync({ ...reconcileScope, dryRun });
      if (dryRun) {
        setPreview(result);
      } else {
        toast.success("Energy records reconciled", { description: `${result.updated} updated, ${result.created} created from submissions.` });
        setPreview(null);
        setReconcileOpen(false);
      }
    } catch (error) {
      toast.error(dryRun ? "Preview failed" : "Reconciliation failed", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const columns: Column<EnergyRecord>[] = [
    { key: "id", header: "Record", sortable: true, value: (r) => r.id, render: (r) => <span className="font-medium">{r.id}</span> },
    { key: "facility", header: "Facility", sortable: true, value: (r) => facilityName(r.facilityId) },
    { key: "month", header: "Month", sortable: true, value: (r) => r.month },
    { key: "stream", header: "Energy stream", sortable: true, value: (r) => r.stream },
    { key: "qty", header: "Quantity", sortable: true, align: "right", value: (r) => r.quantity, render: (r) => (
      <span className="tabular">{fmt(r.quantity)} <span className="text-muted-foreground">{r.unit}</span></span>
    ) },
    { key: "variance", header: "MoM variance", sortable: true, align: "right", value: (r) => r.variance, render: (r) => (
      <span className={r.variance > 10 ? "tabular text-destructive" : r.variance < -5 ? "tabular text-success" : "tabular"}>
        {r.variance > 0 ? "+" : ""}{r.variance}%
      </span>
    ) },
    { key: "cost", header: "Cost (₹)", sortable: true, align: "right", value: (r) => r.cost, render: (r) => <span className="tabular">{fmt(r.cost)}</span> },
    { key: "meter", header: "Meter ref", value: (r) => r.meterRef },
    { key: "validation", header: "Validation", sortable: true, value: (r) => r.validation, render: (r) => <StatusBadge value={r.validation} /> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Operations"
        title="Energy Management"
        description="Consumption of purchased and generated energy across facilities, reconciled against meters and invoices before carbon calculation."
        actions={
          <div className="flex gap-2">
            {canReconcile && (
              <Button variant="outline" onClick={() => setReconcileOpen(true)}>
                <RefreshCw className="size-4" /> Reconcile with submissions
              </Button>
            )}
            <Button variant="outline" disabled={rows.length === 0} onClick={exportCsv}>
              <Download className="size-4" /> Export dataset
            </Button>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Energy cost" value={`₹${(totalCost / 10_000_000).toFixed(2)} Cr`} hint={`Period: ${periodLabel}`} icon={<Zap className="size-4" />} tone="info" />
        <StatCard label="Renewable share" value={`${renewableShare}%`} hint={`Of total electricity supply · ${periodLabel}`} icon={<Sparkles className="size-4" />} tone="success" />
        <StatCard label="Energy consumed" value={`${energyTj.toFixed(1)} TJ`} hint={`Electricity + diesel + gas · ${periodLabel}`} icon={<Gauge className="size-4" />} />
        <StatCard label="Open anomalies" value={anomalies.length} hint={`Anomalous or missing meter data · ${periodLabel}`} icon={<AlertTriangle className="size-4" />} tone="warning" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Select value={facility} onValueChange={setFacility}>
          <SelectTrigger className="h-9 w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All facilities</SelectItem>
            {allFacilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.active === false ? `${f.name} (inactive)` : f.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={stream} onValueChange={setStream}>
          <SelectTrigger className="h-9 w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All energy streams</SelectItem>
            {["Electricity", "Diesel", "Natural Gas", "Steam", "Renewable Energy"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={basis} onValueChange={(v) => setBasis(v as Basis)}>
          <SelectTrigger className="h-9 w-56" title="Which records feed the KPIs, charts and consumption records"><SelectValue /></SelectTrigger>
          <SelectContent>
            {(Object.keys(BASIS_LABEL) as Basis[]).map((b) => <SelectItem key={b} value={b}>{BASIS_LABEL[b]}</SelectItem>)}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          From
          <Input type="month" className="h-9 w-40" aria-label="From month" value={from} min={months[0]} max={to || months[months.length - 1]} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          To
          <Input type="month" className="h-9 w-40" aria-label="To month" value={to} min={from || months[0]} max={months[months.length - 1]} onChange={(e) => setTo(e.target.value)} />
        </label>
        {from || to ? <Button variant="ghost" size="sm" onClick={() => { setFrom(""); setTo(""); }}>All periods</Button> : null}
        {rangeBad ? <span className="text-xs text-destructive">“From” is after “To” — nothing matches.</span> : null}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="records">Consumption records</TabsTrigger>
        </TabsList>

        <TabsContent value="analytics" className="space-y-4 pt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard title="Consumption by energy stream" description={`Thousands of native units per month — kWh (electricity, renewable), L (diesel), SCM (gas), t (steam). Bars are grouped, not stacked, because units differ.${stream === "all" ? "" : ` Showing ${stream} only.`}`}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={trend} margin={{ left: 8, top: 8, bottom: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="month" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Reporting month", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Quantity (thousand units)", angle: -90, position: "insideLeft", fontSize: 12, fill: "var(--muted-foreground)", style: { textAnchor: "middle" } }} />
                    <RTooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, name) => [`${Number(v).toLocaleString("en-IN")} thousand ${STREAM_UNIT[String(name)] ?? ""}`, name]}
                      labelFormatter={(l) => `Month ${l}`}
                    />
                    <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} />
                    {[["Electricity", "Electricity", 1], ["Natural gas", "Natural Gas", 2], ["Diesel", "Diesel", 3], ["Steam", "Steam", 5], ["Renewable", "Renewable Energy", 4]].map(([key, st, c]) =>
                      stream === "all" || stream === st ? <Bar key={String(key)} dataKey={String(key)} name={String(key)} fill={`var(--chart-${c})`} radius={[3, 3, 0, 0]} /> : null,
                    )}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>

            <SectionCard title="Energy consumption trend" description={stream === "Steam" || stream === "Renewable Energy" ? "Energy content (GJ) is not derived for steam or renewable generation, so this trend is empty for the selected stream." : "Energy content of the selected stream(s) (electricity, diesel, gas), terajoules per month"}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ left: 8, bottom: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="month" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Reporting month", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Energy (TJ)", angle: -90, position: "insideLeft", fontSize: 12, fill: "var(--muted-foreground)", style: { textAnchor: "middle" } }} />
                    <RTooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                      formatter={(v) => [`${Number(v).toLocaleString("en-IN")} TJ`, "Energy"]}
                      labelFormatter={(l) => `Month ${l}`}
                    />
                    <Line type="monotone" dataKey="intensity" stroke="var(--chart-1)" strokeWidth={2.5} dot={{ r: 3 }} name="Energy (TJ)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          </div>

          <SectionCard title="Anomaly detection" description={`Records outside the ±${rules?.energyVariancePct ?? 14}% variance band or with missing meter data`}>
            {anomalies.length === 0 ? (
              <p className="text-sm text-muted-foreground">No anomalies detected for the current selection.</p>
            ) : (
              <ul className="divide-y divide-border">
                {anomalies.slice(0, 6).map((a) => (
                  <li key={a.id} className="flex items-start justify-between gap-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{a.stream} · {facilityName(a.facilityId)}</p>
                      <p className="text-xs text-muted-foreground">
                        {a.month} · {a.validation === "Missing" ? "No meter reading recorded" : `Variance ${a.variance > 0 ? "+" : ""}${a.variance}% vs previous month`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge value={a.validation} />
                      <Button size="sm" variant="outline" onClick={() => openDetail(a)}>Investigate</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </TabsContent>

        <TabsContent value="records" className="pt-4">
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(r) => r.id}
            pageSize={10}
            onRowClick={openDetail}
            searchKeys={(r) => `${r.id} ${facilityName(r.facilityId)} ${r.stream} ${r.meterRef} ${r.invoiceRef}`}
            searchPlaceholder="Search meter, invoice or record ID…"
          />
        </TabsContent>
      </Tabs>

      <Sheet open={!!detail} onOpenChange={(o) => !o && openDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>{detail.stream}</SheetTitle>
                <SheetDescription>{facilityName(detail.facilityId)} · {detail.month} · {detail.id}</SheetDescription>
              </SheetHeader>
              <div className="grid grid-cols-2 gap-4 px-4 pb-8">
                <Field label="Quantity" value={`${fmt(detail.quantity)} ${detail.unit}`} />
                <Field label="Cost" value={`₹${fmt(detail.cost)}`} />
                <Field label="Meter reference" value={detail.meterRef} />
                <Field label="Invoice reference" value={detail.invoiceRef} />
                <Field label="Month-on-month variance" value={`${detail.variance > 0 ? "+" : ""}${detail.variance}%`} />
                <Field label="Validation" value={<StatusBadge value={detail.validation} />} />
                <Field label="Energy content" value={detail.energyGj != null ? `${fmt(detail.energyGj)} GJ` : detail.submissionId ? "Not counted (steam / renewable)" : "Pending reconciliation"} />
                <Field label="Source submission" value={detail.submissionId ?? "Not linked — run reconciliation"} />
                <p className="col-span-2 text-xs text-muted-foreground">
                  Quantity, variance and validation are derived from the monthly submission and cannot be edited here — correct the submission instead.
                </p>
                {!canEdit && (
                  <p className="col-span-2 rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                    Meter, invoice and cost can be edited by roles that may edit energy records (signed in as: {role}).
                  </p>
                )}
                {canEdit && (
                  <div className="col-span-2 space-y-3 rounded-lg border border-border p-3">
                    <p className="text-sm font-medium">Procurement details</p>
                    <div className="space-y-1.5"><Label htmlFor="en-meter">Meter reference</Label><Input id="en-meter" value={edit.meterRef} onChange={(e) => setEdit({ ...edit, meterRef: e.target.value })} /></div>
                    <div className="space-y-1.5"><Label htmlFor="en-inv">Invoice reference</Label><Input id="en-inv" value={edit.invoiceRef} onChange={(e) => setEdit({ ...edit, invoiceRef: e.target.value })} /></div>
                    <div className="space-y-1.5"><Label htmlFor="en-cost">Cost (₹)</Label><Input id="en-cost" inputMode="decimal" value={edit.cost} onChange={(e) => setEdit({ ...edit, cost: e.target.value })} /></div>
                    <Button onClick={saveEdit} disabled={updateEnergy.isPending}>{updateEnergy.isPending ? "Saving…" : "Save changes"}</Button>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <Dialog open={reconcileOpen} onOpenChange={(o) => { setReconcileOpen(o); if (!o) setPreview(null); }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Reconcile energy records with submissions</DialogTitle>
            <DialogDescription>
              Recomputes quantity, variance and validation from the monthly submissions (the single source of truth). Scope:{" "}
              {reconcileScope.facilityId ? facilityName(reconcileScope.facilityId) : "All facilities"} · {reconcileScope.month ?? "all periods"}.
              Locked periods are skipped; meter, invoice and cost are never overwritten.
              Energy records already update automatically whenever a submission is saved, approved or rejected — use this only to repair records created before that link existed or after a conversion-factor or rule change. Preview first; nothing is written until you apply.
            </DialogDescription>
          </DialogHeader>
          {preview ? (
            <div className="space-y-3 text-sm">
              <p className="tabular">{preview.evaluated} submission(s) checked · <b>{preview.updated}</b> to update · <b>{preview.created}</b> to create · {preview.unchanged} unchanged</p>
              {preview.items.length > 0 && (
                <div className="max-h-56 overflow-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 text-left"><tr><th className="p-2">Record</th><th className="p-2 text-right">Quantity</th><th className="p-2">Validation</th><th className="p-2 text-right">Variance</th></tr></thead>
                    <tbody>
                      {preview.items.map((i) => (
                        <tr key={i.id} className="border-t">
                          <td className="p-2">{i.id}</td>
                          <td className="tabular p-2 text-right">{i.oldQuantity === i.newQuantity ? fmt(i.newQuantity) : `${i.oldQuantity === null ? "—" : fmt(i.oldQuantity)} → ${fmt(i.newQuantity)}`}</td>
                          <td className="p-2">{i.excluded ? <span className="text-muted-foreground">Hidden — submission is draft/rejected</span> : i.oldValidation === i.newValidation ? i.newValidation : `${i.oldValidation ?? "—"} → ${i.newValidation}`}</td>
                          <td className="tabular p-2 text-right">{i.oldVariance === i.newVariance ? `${i.newVariance}%` : `${i.oldVariance ?? "—"}% → ${i.newVariance}%`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {preview.skipped.length > 0 && <ul className="space-y-1 text-xs text-muted-foreground">{preview.skipped.map((k, idx) => <li key={idx}>Skipped {k.target}: {k.reason}</li>)}</ul>}
              {preview.created + preview.updated === 0 && <p className="text-muted-foreground">Nothing to change — energy records already match the submissions.</p>}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Preview first: nothing is written until you apply.</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => runReconcile(true)} disabled={reconcile.isPending}>Preview changes</Button>
            <Button onClick={() => runReconcile(false)} disabled={reconcile.isPending || !preview || preview.created + preview.updated === 0}>Apply</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
