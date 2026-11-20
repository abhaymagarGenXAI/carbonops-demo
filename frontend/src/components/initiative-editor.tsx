import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "@/components/page-parts";
import { useUpdateInitiative } from "@/hooks/useApi";
import type { Initiative } from "@/types/domain";

/** Manager-only editor: milestone checklist (drives completion/status), verified (M&V) reduction, annual savings. */
export function InitiativeEditor({ initiative, onSaved }: { initiative: Initiative; onSaved: (i: Initiative) => void }) {
  const update = useUpdateInitiative();
  const [ms, setMs] = useState(initiative.milestones);
  const [actual, setActual] = useState(String(initiative.actualReduction));
  const [savings, setSavings] = useState(String(initiative.annualSavings ?? 0));
  useEffect(() => {
    setMs(initiative.milestones);
    setActual(String(initiative.actualReduction));
    setSavings(String(initiative.annualSavings ?? 0));
  }, [initiative]);

  const save = () => {
    const a = Number(actual), s = Number(savings);
    if (!(a >= 0) || !(s >= 0)) return toast.error("Reduction and savings must be zero or more");
    if (ms.some((m) => !m.name.trim() || !m.date)) return toast.error("Every milestone needs a name and a date");
    return update
      .mutateAsync({ id: initiative.id, patch: { actualReduction: a, annualSavings: s, milestones: ms.map((m) => ({ ...m, name: m.name.trim() })) } })
      .then((i) => { toast.success(`${i.id} updated`, { description: `Completion ${i.completion}% · status ${i.status}` }); onSaved(i); })
      .catch((e: unknown) => toast.error("Could not save", { description: e instanceof Error ? e.message : "Unexpected error" }));
  };

  return (
    <SectionCard title="Update progress" description="Ticking milestones sets completion and status. Enter the actual reduction only from measurement / M&V — it is never estimated.">
      <ul className="space-y-2">
        {ms.map((m, i) => (
          <li key={i} className="flex items-center gap-2">
            <input type="checkbox" aria-label={`Milestone ${i + 1} done`} checked={m.done} onChange={(e) => setMs(ms.map((x, j) => (j === i ? { ...x, done: e.target.checked } : x)))} />
            <Input className="h-8 flex-1" value={m.name} onChange={(e) => setMs(ms.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <Input className="h-8 w-36" type="date" value={m.date} onChange={(e) => setMs(ms.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} />
            <Button type="button" size="icon" variant="ghost" aria-label="Remove milestone" onClick={() => setMs(ms.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
          </li>
        ))}
      </ul>
      <Button type="button" size="sm" variant="outline" className="mt-2" disabled={ms.length >= 20} onClick={() => setMs([...ms, { name: "", date: initiative.endDate, done: false }])}><Plus className="size-4" /> Add milestone</Button>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div><Label htmlFor="ie-act">Verified reduction (tCO₂e/yr)</Label><Input id="ie-act" type="number" value={actual} onChange={(e) => setActual(e.target.value)} /></div>
        <div><Label htmlFor="ie-sav">Annual savings (₹/yr)</Label><Input id="ie-sav" type="number" value={savings} onChange={(e) => setSavings(e.target.value)} /></div>
      </div>
      <Button className="mt-4 w-full" onClick={save} disabled={update.isPending}>Save progress</Button>
    </SectionCard>
  );
}
