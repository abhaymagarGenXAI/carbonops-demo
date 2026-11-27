import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Info } from "lucide-react";
import { EmptyState, SectionCard, StatCard } from "@/components/page-parts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useForecast } from "@/hooks/useApi";
import type { TargetOutlook } from "@/types/domain";

const fmt = (n: number | undefined | null, d = 1) => (n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: d }));
type ScopeKey = "Total" | "Scope 1" | "Scope 2";

/** Statistical trend forecast (least squares + prediction band) of approved, complete months — no AI involved. */
export function ForecastPanel() {
  const [horizon, setHorizon] = useState("12");
  const [scope, setScope] = useState<ScopeKey>("Total");
  const { data, isLoading, error } = useForecast(Number(horizon));

  const rows = useMemo(() => {
    const s = data?.scopes?.[scope];
    if (!s) return [];
    return [
      // the projected line starts from the last actual point so the two lines join
      ...s.history.map((h, i) => ({ month: h.month, actual: h.value, ...(i === s.history.length - 1 ? { projected: h.value } : {}) })),
      ...s.projection.map((p) => ({ month: p.month, projected: p.value, band: [p.low, p.high] as [number, number] })),
    ];
  }, [data, scope]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading forecast…</p>;
  if (error || !data) return <EmptyState title="Forecast unavailable" hint={error instanceof Error ? error.message : "Try again shortly."} />;

  const s = data.scopes?.[scope];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={scope} onValueChange={(v) => setScope(v as ScopeKey)}>
          <SelectTrigger className="h-8 w-36" aria-label="Forecast scope"><SelectValue /></SelectTrigger>
          <SelectContent>{["Total", "Scope 1", "Scope 2"].map((x) => <SelectItem key={x} value={x}>{x === "Total" ? "Scope 1 + 2" : x}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={horizon} onValueChange={setHorizon}>
          <SelectTrigger className="h-8 w-40" aria-label="Forecast horizon"><SelectValue /></SelectTrigger>
          <SelectContent>{["6", "12", "18", "24"].map((x) => <SelectItem key={x} value={x}>Next {x} months</SelectItem>)}</SelectContent>
        </Select>
      </div>

      {data.warnings.map((w) => (
        <p key={w} className="flex items-start gap-2 rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <Info className="mt-0.5 size-4 shrink-0" /> {w}
        </p>
      ))}

      {!data.available || !s ? (
        <EmptyState title="Not enough approved history yet" hint={`Needs ${data.minMonths}+ consecutive months approved for every facility; ${data.usedMonths.length} available.`} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-4">
            <StatCard label="Trend" value={`${s.fit.slopePerMonth >= 0 ? "+" : ""}${fmt(s.fit.slopePerMonth)} tCO₂e/month`} hint={`${s.fit.slopePctPerMonth >= 0 ? "+" : ""}${s.fit.slopePctPerMonth}% of the average month`} />
            <StatCard label="Fit (R²)" value={s.fit.r2.toFixed(2)} hint="1.00 = months follow a straight line exactly" />
            <StatCard label="Months used" value={s.fit.months} hint={`${data.usedMonths[0]} → ${data.usedMonths[data.usedMonths.length - 1]}`} />
            <StatCard label={`Projected ${s.projection[s.projection.length - 1]!.month}`} value={`${fmt(s.projection[s.projection.length - 1]!.value, 0)} tCO₂e`}
              hint={`95% band ${fmt(s.projection[s.projection.length - 1]!.low, 0)} – ${fmt(s.projection[s.projection.length - 1]!.high, 0)}`} />
          </div>

          <SectionCard title="Monthly emissions: approved history and trend projection" description="tCO₂e per month, approved and complete months only. Shaded area = approximate 95% prediction band.">
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={rows} margin={{ left: 8, right: 8, bottom: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} label={{ value: "Month", position: "insideBottom", offset: -10, fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => fmt(v, 0)} label={{ value: "tCO₂e / month", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <RTooltip formatter={(v: number | number[], n: string) => [Array.isArray(v) ? `${fmt(v[0], 0)} – ${fmt(v[1], 0)}` : `${fmt(v, 1)} tCO₂e`, n === "band" ? "95% band" : n === "actual" ? "Approved actual" : "Trend projection"]} />
                  <Area dataKey="band" stroke="none" fill="var(--chart-3)" fillOpacity={0.18} isAnimationActive={false} />
                  <Line dataKey="actual" stroke="var(--chart-1)" strokeWidth={2} dot connectNulls={false} isAnimationActive={false} />
                  <Line dataKey="projected" stroke="var(--chart-3)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          <SectionCard title="Outlook against targets" description="Where the trend line will be in December of each target year, versus the monthly level the target allows then.">
            {data.outlook.length === 0 ? (
              <EmptyState title="No targets to compare" hint="Set a baseline and targets under Targets & baseline." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2">Target</th><th className="text-right">Projected / month</th><th className="text-right">Allowed / month</th><th className="text-right">Gap</th><th className="pl-4">Verdict</th>
                  </tr></thead>
                  <tbody>{data.outlook.map((o: TargetOutlook) => (
                    <tr key={o.scope} className="border-t">
                      <td className="py-2">{o.scope === "Total" ? "Scope 1 + 2" : o.scope}: −{o.reductionPct}% by Dec {o.targetYear}</td>
                      {o.applicable ? (<>
                        <td className="text-right tabular">{fmt(o.projectedMonthly, 0)} <span className="text-xs text-muted-foreground">({fmt(o.projectedLow, 0)}–{fmt(o.projectedHigh, 0)})</span></td>
                        <td className="text-right tabular">{fmt(o.allowedMonthly, 0)}</td>
                        <td className="text-right tabular">{(o.gapMonthly ?? 0) > 0 ? "+" : ""}{fmt(o.gapMonthly, 0)}{o.gapPct != null ? ` (${o.gapPct}%)` : ""}</td>
                        <td className="pl-4"><span className="font-medium">{o.verdict}</span><span className="block text-xs text-muted-foreground">{o.certainty}</span></td>
                      </>) : <td colSpan={4} className="text-muted-foreground">Target year already reached or passed</td>}
                    </tr>))}</tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </>
      )}
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">{data.method.map((m) => <li key={m}>{m}</li>)}</ul>
    </div>
  );
}
