import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { SectionCard } from "@/components/page-parts";
import { useInitiativeAnalysis, useSaveAssumptions } from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";

const fmt = (n: number | null | undefined, d = 0) => (n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: d }));

export function InitiativeAnalysis() {
  const { facilityName } = useStore();
  const { can } = useAuth();
  const canEdit = can("initiative.manage");
  const { data, isLoading } = useInitiativeAnalysis();
  const save = useSaveAssumptions();
  const [form, setForm] = useState({ carbonValuePerTonne: "", discountRatePct: "", lifetimeYears: "" });
  useEffect(() => {
    if (data) setForm({ carbonValuePerTonne: String(data.assumptions.carbonValuePerTonne), discountRatePct: String(data.assumptions.discountRatePct), lifetimeYears: String(data.assumptions.lifetimeYears) });
  }, [data]);
  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading analysis…</p>;

  const onSave = () =>
    save
      .mutateAsync({ carbonValuePerTonne: Number(form.carbonValuePerTonne), discountRatePct: Number(form.discountRatePct), lifetimeYears: Number(form.lifetimeYears) })
      .then(() => toast.success("Assumptions saved", { description: "ROI, payback and cost per tonne are recalculated for every initiative." }))
      .catch((e: unknown) => toast.error("Assumptions not saved", { description: e instanceof Error ? e.message : "Unexpected error" }));

  const cov = data.targetCoverage;
  const macc = data.macc.map((r) => ({ ...r, label: `${r.id} · ${r.name.split("—")[0]!.trim().slice(0, 22)}` }));

  return (
    <div className="space-y-4">
      <SectionCard title="Contribution to the emissions target" description="Compares initiatives with the annual reduction the Total target requires (Carbon Accounting → Targets & baseline).">
        {cov ? (
          <div className="space-y-3">
            <p className="text-sm">
              The Total target (−{cov.reductionPct}% by {cov.targetYear}) needs <b>{fmt(cov.gapAnnual)} tCO₂e/yr</b> of reduction.
              Delivered (verified) {fmt(cov.delivered)} + pipeline {fmt(cov.pipeline)} ={" "}
              <b>{cov.coveragePct == null ? "—" : `${cov.coveragePct}%`}</b> covered.
            </p>
            <Progress value={Math.min(100, cov.coveragePct ?? 0)} className="h-2" />
            <p className="text-xs text-muted-foreground">
              {cov.uncovered > 0 ? `Uncovered gap: ${fmt(cov.uncovered)} tCO₂e/yr — more or larger initiatives are needed. ` : "The planned portfolio closes the gap. "}
              {cov.onHold > 0 ? `${fmt(cov.onHold)} tCO₂e/yr sits in On Hold projects and is not counted.` : ""}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {data.baselineSet ? "Add a Total reduction target to see how far the portfolio goes." : "Set a baseline and a Total target in Carbon Accounting → Targets & baseline to see coverage."}
          </p>
        )}
      </SectionCard>

      <SectionCard title="Marginal abatement cost curve" description="Planned and in-progress initiatives, cheapest abatement first. Negative cost = saves more than it costs. Completed and on-hold projects are excluded.">
        {macc.length === 0 ? (
          <p className="text-sm text-muted-foreground">No open initiatives with an expected reduction.</p>
        ) : (
          <div style={{ height: Math.max(240, macc.length * 44 + 70) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={macc} layout="vertical" margin={{ left: 30, right: 20, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis type="number" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Marginal abatement cost (₹ per tCO₂e)", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                <YAxis type="category" dataKey="label" width={190} stroke="var(--muted-foreground)" fontSize={11} />
                <ReferenceLine x={0} stroke="var(--muted-foreground)" />
                <RTooltip
                  contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v, _n, p) => [`₹${fmt(Number(v))}/tCO₂e · ${fmt(p.payload.expectedReduction)} tCO₂e/yr (cumulative ${fmt(p.payload.cumulativeReduction)})`, "Cost"]}
                />
                <Bar dataKey="maccCost" radius={[0, 3, 3, 0]}>
                  {macc.map((r) => <Cell key={r.id} fill={r.maccCost < 0 ? "var(--chart-2)" : "var(--chart-1)"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Measured facility reduction" description="Approved emissions after the baseline vs the baseline, per facility — measured, not estimated. Several initiatives at one facility share the result, so it is not attributed to any single one.">
        {data.facilityMeasured.length === 0 ? (
          <p className="text-sm text-muted-foreground">{data.baselineSet ? "Re-set the baseline (Targets & baseline) to capture per-facility reference levels." : "Needs a baseline (Carbon Accounting → Targets & baseline)."}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr><th className="py-1 pr-3">Facility</th><th className="pr-3">Initiatives</th><th className="pr-3 text-right">Planned (tCO₂e/yr)</th><th className="pr-3 text-right">Verified (tCO₂e/yr)</th><th className="pr-3 text-right">Baseline (tCO₂e/mo)</th><th className="pr-3 text-right">Now (tCO₂e/mo)</th><th className="text-right">Measured cut (tCO₂e/yr)</th></tr>
              </thead>
              <tbody>
                {data.facilityMeasured.map((f) => (
                  <tr key={f.facilityId} className="border-t border-border">
                    <td className="py-1.5 pr-3">{facilityName(f.facilityId)}</td>
                    <td className="pr-3 text-xs text-muted-foreground">{f.initiativeIds.join(", ")}</td>
                    <td className="pr-3 text-right tabular-nums">{fmt(f.plannedAnnual)}</td>
                    <td className="pr-3 text-right tabular-nums">{fmt(f.verifiedAnnual)}</td>
                    <td className="pr-3 text-right tabular-nums">{fmt(f.baselineMonthly)}</td>
                    <td className="pr-3 text-right tabular-nums">{f.actualMonthly == null ? "no data yet" : fmt(f.actualMonthly)}</td>
                    <td className={`text-right font-medium tabular-nums ${(f.measuredAnnualReduction ?? 0) < 0 ? "text-destructive" : ""}`}>{fmt(f.measuredAnnualReduction)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Economic assumptions" description={canEdit ? "Used for ROI, payback and cost per tonne of every initiative." : "Read-only — set by a Sustainability Manager"}>
        <div className="flex flex-wrap items-end gap-4">
          <div><Label htmlFor="as-cv">Carbon value (₹/tCO₂e)</Label><Input id="as-cv" className="w-36" type="number" disabled={!canEdit} value={form.carbonValuePerTonne} onChange={(e) => setForm({ ...form, carbonValuePerTonne: e.target.value })} /></div>
          <div><Label htmlFor="as-dr">Discount rate (%)</Label><Input id="as-dr" className="w-28" type="number" disabled={!canEdit} value={form.discountRatePct} onChange={(e) => setForm({ ...form, discountRatePct: e.target.value })} /></div>
          <div><Label htmlFor="as-ly">Lifetime (years)</Label><Input id="as-ly" className="w-28" type="number" disabled={!canEdit} value={form.lifetimeYears} onChange={(e) => setForm({ ...form, lifetimeYears: e.target.value })} /></div>
          {canEdit ? <Button onClick={onSave} disabled={save.isPending}>Save assumptions</Button> : null}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Annualised cost = investment × capital-recovery factor (discount rate, lifetime). Cost per tonne = (annualised cost − annual savings) ÷ expected reduction.
          ROI = (expected reduction × carbon value + annual savings) ÷ investment. Payback = investment ÷ that annual benefit.
        </p>
      </SectionCard>
    </div>
  );
}
