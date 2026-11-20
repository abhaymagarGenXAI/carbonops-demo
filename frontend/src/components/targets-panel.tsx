import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, Tooltip as RTooltip, XAxis, YAxis, ResponsiveContainer } from "recharts";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useSaveBaseline, useSaveTargets, useTargets } from "@/hooks/useApi";
import { useStore } from "@/lib/store";
import type { EmissionTarget, TargetScope } from "@/types/domain";

const SCOPES: TargetScope[] = ["Total", "Scope 1", "Scope 2"];
const fmt = (n: number | null | undefined, d = 0) => (n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: d }));

export function TargetsPanel() {
  const { role, reportingPeriods } = useStore();
  const canEdit = role === "Sustainability Manager";
  const { data, isLoading } = useTargets();
  const saveBaseline = useSaveBaseline();
  const saveTargets = useSaveTargets();
  const months = useMemo(() => reportingPeriods.map((p) => p.period), [reportingPeriods]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState<Record<TargetScope, { on: boolean; pct: string; year: string }>>({
    Total: { on: false, pct: "", year: "" }, "Scope 1": { on: false, pct: "", year: "" }, "Scope 2": { on: false, pct: "", year: "" },
  });
  const [chartScope, setChartScope] = useState<TargetScope>("Total");

  useEffect(() => {
    if (!data) return;
    setRows((cur) => {
      const next = { ...cur };
      for (const s of SCOPES) {
        const t = data.targets.find((x) => x.scope === s);
        next[s] = t ? { on: true, pct: String(t.reductionPct), year: String(t.targetYear) } : { on: false, pct: cur[s].pct, year: cur[s].year };
      }
      return next;
    });
    if (data.baseline) { setStart(data.baseline.start); setEnd(data.baseline.end); }
  }, [data]);

  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading targets…</p>;
  const fail = (title: string) => (e: unknown) => toast.error(title, { description: e instanceof Error ? e.message : "Unexpected error" });
  const base = data.baseline;
  const targeted = data.targets.map((t) => t.scope);
  const shown: TargetScope = targeted.includes(chartScope) ? chartScope : (targeted[0] ?? "Total");

  const onBaseline = () =>
    saveBaseline.mutateAsync({ start, end }).then(() => toast.success("Baseline saved", { description: `${start} … ${end}, from approved emissions.` })).catch(fail("Baseline not saved"));
  const onTargets = () => {
    const list: EmissionTarget[] = [];
    for (const s of SCOPES) {
      const r = rows[s];
      if (!r.on) continue;
      const pct = Number(r.pct), year = Number(r.year);
      if (!(pct > 0 && pct <= 100) || !Number.isInteger(year)) return toast.error(`${s}: enter a reduction % (1–100) and a target year`);
      list.push({ scope: s, reductionPct: pct, targetYear: year });
    }
    return saveTargets.mutateAsync(list).then(() => toast.success("Targets saved")).catch(fail("Targets not saved"));
  };

  const chart = data.series.map((r) => ({ month: r.month, Actual: r.actual[shown], "Target path": r.allowed[shown] ?? null }));

  return (
    <div className="space-y-4">
      <SectionCard
        title="How this works"
        description="Everything here is computed from approved emission records — nothing is typed in."
      >
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          <li>Only <b>Approved</b> records count. A month counts only when <b>every facility</b> has approved records for it, so a half-approved month never looks like a reduction.</li>
          <li>The <b>baseline</b> is a frozen snapshot of a chosen 1–12 month range; its monthly average is the reference level.</li>
          <li>A <b>target</b> is a % cut from that level reached by December of the target year, falling in a straight line month by month. Status compares cumulative actual with cumulative allowed: On track, At risk (within {data.atRiskTolerancePct}%) or Off track.</li>
        </ul>
      </SectionCard>

      <SectionCard title="Baseline" description={base ? `Frozen ${base.setAt} by ${base.setBy}` : "No baseline yet — choose a period with approved data for every facility"}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {base ? (
            <>
              <StatCard label="Baseline period" value={`${base.start} → ${base.end}`} hint={`${base.months} month(s) · ${base.facilities} facilities · ${base.recordCount} approved records`} />
              <StatCard label="Baseline total" value={`${fmt(base.total)} tCO₂e`} hint={`Annualised ${fmt(base.annualTotal)} tCO₂e`} />
              <StatCard label="Scope 1" value={`${fmt(base.scope1)} tCO₂e`} hint={`Annualised ${fmt(base.annualScope1)}`} />
              <StatCard label="Scope 2" value={`${fmt(base.scope2)} tCO₂e`} hint={`Annualised ${fmt(base.annualScope2)}`} />
            </>
          ) : null}
        </div>
        {canEdit ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-sm">{base ? "Re-baseline:" : "Baseline from"}</span>
            {[{ label: "From", val: start, set: setStart }, { label: "To", val: end, set: setEnd }].map(({ label, val, set }) => (
              <Select key={label} value={val} onValueChange={set}>
                <SelectTrigger className="h-9 w-36" aria-label={`Baseline ${label}`}><SelectValue placeholder={`${label} month`} /></SelectTrigger>
                <SelectContent>
                  {months.filter((m) => !data.completeThrough || m <= data.completeThrough).map((m) => <SelectItem key={m} value={m}>{label} {m}</SelectItem>)}
                </SelectContent>
              </Select>
            ))}
            <Button onClick={onBaseline} disabled={!start || !end || saveBaseline.isPending}>{base ? "Re-baseline" : "Set baseline"}</Button>
            <span className="text-xs text-muted-foreground">Fully approved months so far: up to {data.completeThrough ?? "none"}.</span>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Reduction targets" description={canEdit ? "Choose the scopes to target" : "Read-only — set by a Sustainability Manager"}>
        {!base ? (
          <p className="text-sm text-muted-foreground">Set a baseline first.</p>
        ) : (
          <fieldset disabled={!canEdit} className="space-y-2">
            {SCOPES.map((s) => (
              <div key={s} className="flex flex-wrap items-center gap-3">
                <Switch checked={rows[s].on} onCheckedChange={(v) => setRows({ ...rows, [s]: { ...rows[s], on: v } })} aria-label={`Target for ${s}`} />
                <span className="w-16 text-sm">{s}</span>
                <span className="text-xs text-muted-foreground">reduce by</span>
                <Input className="h-8 w-20" type="number" min={1} max={100} value={rows[s].pct} disabled={!rows[s].on} onChange={(e) => setRows({ ...rows, [s]: { ...rows[s], pct: e.target.value } })} />
                <span className="text-xs text-muted-foreground">% by end of</span>
                <Input className="h-8 w-24" type="number" value={rows[s].year} disabled={!rows[s].on} onChange={(e) => setRows({ ...rows, [s]: { ...rows[s], year: e.target.value } })} />
              </div>
            ))}
            {canEdit ? <Button className="mt-2" onClick={onTargets} disabled={saveTargets.isPending}>Save targets</Button> : null}
          </fieldset>
        )}
      </SectionCard>

      {data.progress.length ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {data.progress.map((p) => (
              <SectionCard key={p.scope} title={`${p.scope}: −${p.reductionPct}% by ${p.targetYear}`} description={p.latestMonth ? `Latest complete month ${p.latestMonth} · ${p.monthsEvaluated} month(s) tracked` : "No complete month after the baseline yet"} actions={<StatusBadge value={p.status} />}>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <dt className="text-muted-foreground">Cut achieved (latest month)</dt><dd className="text-right font-medium">{p.achievedReductionPct == null ? "—" : `${p.achievedReductionPct}%`}</dd>
                  <dt className="text-muted-foreground">Cut required by now</dt><dd className="text-right font-medium">{p.requiredReductionPct == null ? "—" : `${p.requiredReductionPct}%`}</dd>
                  <dt className="text-muted-foreground">Actual since baseline</dt><dd className="text-right font-medium">{fmt(p.cumulativeActual)} tCO₂e</dd>
                  <dt className="text-muted-foreground">Allowed since baseline</dt><dd className="text-right font-medium">{fmt(p.cumulativeAllowed)} tCO₂e</dd>
                  <dt className="text-muted-foreground">Annual baseline → target</dt><dd className="text-right font-medium">{fmt(p.baselineAnnual)} → {fmt(p.targetAnnual)}</dd>
                </dl>
              </SectionCard>
            ))}
          </div>

          <SectionCard
            title="Trajectory vs actual"
            description={`Monthly tCO₂e, approved records only${data.incompleteMonths.length ? ` · excluded (not fully approved): ${data.incompleteMonths.join(", ")}` : ""}`}
            actions={
              <Select value={shown} onValueChange={(v) => setChartScope(v as TargetScope)}>
                <SelectTrigger className="h-8 w-32" aria-label="Chart scope"><SelectValue /></SelectTrigger>
                <SelectContent>{targeted.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            }
          >
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart} margin={{ left: 8, bottom: 18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="month" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Reporting month", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                  <YAxis stroke="var(--muted-foreground)" fontSize={12} domain={["auto", "auto"]} label={{ value: "Emissions (tCO₂e / month)", angle: -90, position: "insideLeft", fontSize: 12, fill: "var(--muted-foreground)", style: { textAnchor: "middle" } }} />
                  <RTooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${Number(v).toLocaleString("en-IN")} tCO₂e`, n]} labelFormatter={(l) => `Month ${l}`} />
                  <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="Actual" stroke="var(--chart-1)" strokeWidth={2.5} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="Target path" stroke="var(--chart-3)" strokeWidth={2} strokeDasharray="6 4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
