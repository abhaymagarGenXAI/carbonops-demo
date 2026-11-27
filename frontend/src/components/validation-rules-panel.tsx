import { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionCard } from "@/components/page-parts";
import { useSaveValidationRules, useValidationRules } from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";
import type { ValidationRules } from "@/types/domain";

const FIELDS: Record<string, string> = {
  electricity: "Electricity (kWh)", diesel: "Diesel (L)", naturalGas: "Natural gas (SCM)",
  steam: "Steam (t)", flareGas: "Flare gas (SCM)", methaneLeak: "Methane leakage (kg)",
};

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b py-3 last:border-0">
      <div className="max-w-md"><p className="text-sm font-medium">{label}</p>{hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}</div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

export function ValidationRulesPanel() {
  const { can } = useAuth();
  const canEdit = can("rules.manage");
  const { data, isLoading } = useValidationRules();
  const save = useSaveValidationRules();
  const [rules, setRules] = useState<ValidationRules | null>(null);
  useEffect(() => { if (data) setRules(data); }, [data]);
  if (isLoading || !rules) return <p className="text-sm text-muted-foreground">Loading rules…</p>;

  const set = <K extends keyof ValidationRules>(k: K, v: ValidationRules[K]) => setRules({ ...rules, [k]: v });
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const used = new Set(rules.limits.map((l) => l.field));
  const free = Object.keys(FIELDS).filter((f) => !used.has(f));
  const setLimit = (i: number, patch: Partial<ValidationRules["limits"][number]>) =>
    set("limits", rules.limits.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const onSave = async () => {
    try {
      await save.mutateAsync(rules);
      toast.success("Validation rules saved", { description: "New rules apply to every submission saved from now on; alerts update immediately." });
    } catch (e) {
      toast.error("Could not save rules", { description: e instanceof Error ? e.message : "Unexpected error" });
    }
  };

  return (
    <div className="space-y-4">
      <SectionCard title="Validation rules" description={canEdit ? "Thresholds used to flag activity data. A rule marked Block stops a submission (drafts can always be saved)." : "Read-only — your role cannot change these rules."}>
        <fieldset disabled={!canEdit} className="space-y-1">
          <Row label="Spike detection" hint="Compare each source with the mean of earlier non-draft months.">
            <Switch checked={rules.spikeEnabled} onCheckedChange={(v) => set("spikeEnabled", v)} />
          </Row>
          <Row label="Warn at deviation ≥ (%)"><Input className="h-8 w-24" type="number" value={rules.spikePct} onChange={(e) => set("spikePct", num(e.target.value))} /></Row>
          <Row label="High severity at deviation ≥ (%)"><Input className="h-8 w-24" type="number" value={rules.highPct} onChange={(e) => set("highPct", num(e.target.value))} /></Row>
          <Row label="Reference history (months)" hint="1–12 earlier months form the reference mean."><Input className="h-8 w-24" type="number" value={rules.historyMonths} onChange={(e) => set("historyMonths", num(e.target.value))} /></Row>
          <Row label="Block High spikes" hint="Submission is refused until the data is corrected."><Switch checked={rules.spikeBlockHigh} onCheckedChange={(v) => set("spikeBlockHigh", v)} /></Row>
          <Row label="Zero / missing value check" hint="Zero reported although earlier months were positive.">
            <Switch checked={rules.zeroEnabled} onCheckedChange={(v) => set("zeroEnabled", v)} />
          </Row>
          <Row label="Block zero / missing values"><Switch checked={rules.zeroBlock} onCheckedChange={(v) => set("zeroBlock", v)} /></Row>
          <Row label="Asset inspection interval (days)" hint="Assets (not shut down) not inspected within this interval raise an alert.">
            <Input className="h-8 w-24" type="number" value={rules.inspectionIntervalDays} onChange={(e) => set("inspectionIntervalDays", num(e.target.value))} />
          </Row>
          <Row label="Energy anomaly band ± (%)" hint="Energy Management flags a record whose month-on-month change is beyond this band. Existing records are re-classified when you save.">
            <Input className="h-8 w-24" type="number" value={rules.energyVariancePct} onChange={(e) => set("energyVariancePct", num(e.target.value))} />
          </Row>
        </fieldset>
      </SectionCard>

      <SectionCard title="Absolute monthly limits" description="Flag (or block) a month above a fixed ceiling per source.">
        <fieldset disabled={!canEdit} className="space-y-2">
          {rules.limits.length === 0 ? <p className="text-sm text-muted-foreground">No limits configured.</p> : null}
          {rules.limits.map((l, i) => (
            <div key={l.field} className="flex flex-wrap items-center gap-3">
              <span className="w-44 text-sm">{FIELDS[l.field] ?? l.field}</span>
              <Input className="h-8 w-36" type="number" value={l.max} onChange={(e) => setLimit(i, { max: num(e.target.value) })} />
              <label className="flex items-center gap-1 text-xs">Active <Switch checked={l.enabled} onCheckedChange={(v) => setLimit(i, { enabled: v })} /></label>
              <label className="flex items-center gap-1 text-xs">Block <Switch checked={l.block} onCheckedChange={(v) => setLimit(i, { block: v })} /></label>
              <Button size="icon" variant="ghost" aria-label="Remove limit" onClick={() => set("limits", rules.limits.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </div>
          ))}
          {free.length ? (
            <Select onValueChange={(f) => set("limits", [...rules.limits, { field: f, max: 1000, enabled: true, block: false }])}>
              <SelectTrigger className="h-8 w-52"><Plus className="size-4" /><SelectValue placeholder="Add a limit…" /></SelectTrigger>
              <SelectContent>{free.map((f) => <SelectItem key={f} value={f}>{FIELDS[f]}</SelectItem>)}</SelectContent>
            </Select>
          ) : null}
        </fieldset>
      </SectionCard>

      {canEdit ? <Button onClick={onSave} disabled={save.isPending}><Save className="size-4" /> Save rules</Button> : null}
    </div>
  );
}
