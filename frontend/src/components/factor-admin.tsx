import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DataTable, type Column } from "@/components/data-table";
import { StatusBadge } from "@/components/status-badge";
import { useCreateFactor, useDeleteFactor, useScope3, useScope3Categories, useUpdateFactor } from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";
import type { EmissionFactor, EmissionFactorInput } from "@/types/domain";

const blank: EmissionFactorInput = { source: "", scope: "Scope 3", value: 0, unit: "", reference: "", validFrom: "", status: "Active", category: "" };
const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");

/** Versioned emission factor register. Anyone can read it; only an Administrator edits. A factor cited by records is frozen —
 *  the dialog then offers "New version" (same source, later valid-from) instead of editing the number. */
export function FactorAdmin() {
  const { factors, emissions } = useStore();
  const { user } = useAuth();
  const canEdit = user?.appRole === "Administrator"; // the API allows factor changes for Administrators only
  const { data: categories = [] } = useScope3Categories();
  const { data: s3Entries = [] } = useScope3();
  const create = useCreateFactor(), update = useUpdateFactor(), remove = useDeleteFactor();
  const [dlg, setDlg] = useState<{ mode: "new" | "edit" | "version"; factor?: EmissionFactor | undefined } | null>(null);
  const [f, setF] = useState<EmissionFactorInput>(blank);
  const [scopeFilter, setScopeFilter] = useState("all");

  const cites = (id: string) => emissions.filter((e) => e.factorId === id).length + s3Entries.filter((e) => e.factorId === id).length;
  const open = (mode: "new" | "edit" | "version", factor?: EmissionFactor) => {
    setDlg({ mode, factor });
    if (mode === "new" || !factor) setF(blank);
    else if (mode === "edit") setF({ ...factor, category: factor.category ?? "" });
    else { const { id: _i, ...rest } = factor; setF({ ...rest, validFrom: "", status: "Active", category: factor.category ?? "" }); }
  };

  const save = async () => {
    if (!dlg) return;
    const body = { ...f, value: Number(f.value), source: f.source.trim(), unit: f.unit.trim(), reference: f.reference.trim(), category: f.scope === "Scope 3" ? f.category || null : null };
    if (!body.source || !body.unit || !body.reference || !body.validFrom || !(body.value > 0)) { toast.error("Source, factor (> 0), unit, reference and valid-from date are required"); return; }
    try {
      if (dlg.mode === "edit" && dlg.factor) {
        const { id: _id, ...changes } = body;
        await update.mutateAsync({ id: dlg.factor.id, body: changes });
        toast.success(`${dlg.factor.id} updated`);
      } else {
        const { id: _id, ...rest } = body;
        const made = await create.mutateAsync(rest);
        toast.success(`${made.id} created`, { description: dlg.mode === "version" ? "Older active versions of this source are now superseded; periods before its valid-from date keep the old version." : undefined });
      }
      setDlg(null);
    } catch (e) { toast.error("Could not save the factor", { description: msg(e) }); }
  };

  const del = (x: EmissionFactor) =>
    remove.mutateAsync(x.id).then(() => toast.success(`${x.id} deleted`)).catch((e: unknown) => toast.error("Could not delete", { description: msg(e) }));

  const rows = factors.filter((x) => scopeFilter === "all" || x.scope === scopeFilter);
  const columns: Column<EmissionFactor>[] = [
    { key: "id", header: "ID", value: (x) => x.id, sortable: true },
    { key: "source", header: "Source", value: (x) => x.source, sortable: true, render: (x) => <span>{x.source}{x.category ? <span className="block text-xs text-muted-foreground">Cat {x.category}</span> : null}</span> },
    { key: "scope", header: "Scope", value: (x) => x.scope },
    { key: "value", header: "Factor", align: "right", value: (x) => x.value, render: (x) => <span className="tabular">{x.value} <span className="text-muted-foreground">{x.unit}</span></span> },
    { key: "reference", header: "Reference", value: (x) => x.reference },
    { key: "validFrom", header: "Valid from", sortable: true, value: (x) => x.validFrom },
    { key: "used", header: "Records citing", align: "right", value: (x) => cites(x.id) },
    { key: "status", header: "Status", value: (x) => x.status, render: (x) => <StatusBadge value={x.status} /> },
    ...(canEdit ? [{
      key: "actions", header: "", render: (x: EmissionFactor) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="ghost" aria-label={`Edit ${x.id}`} onClick={() => open("edit", x)}><Pencil className="size-4" /></Button>
          <Button size="sm" variant="outline" onClick={() => open("version", x)}>New version</Button>
          <Button size="icon" variant="ghost" aria-label={`Delete ${x.id}`} disabled={cites(x.id) > 0} title={cites(x.id) ? "Cited by emission records" : "Delete"} onClick={() => del(x)}><Trash2 className="size-4" /></Button>
        </div>
      ),
    } as Column<EmissionFactor>] : []),
  ];
  const frozen = dlg?.mode === "edit" && dlg.factor ? cites(dlg.factor.id) > 0 : false;
  const set = <K extends keyof EmissionFactorInput>(k: K, v: EmissionFactorInput[K]) => setF((p) => ({ ...p, [k]: v }));

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select value={scopeFilter} onValueChange={setScopeFilter}>
          <SelectTrigger className="h-8 w-36" aria-label="Scope filter"><SelectValue /></SelectTrigger>
          <SelectContent>{["all", "Scope 1", "Scope 2", "Scope 3"].map((s) => <SelectItem key={s} value={s}>{s === "all" ? "All scopes" : s}</SelectItem>)}</SelectContent>
        </Select>
        {canEdit
          ? <Button size="sm" className="ml-auto" onClick={() => open("new")}><Plus className="size-4" /> Add factor</Button>
          : <span className="ml-auto text-xs text-muted-foreground">Read-only — factors are maintained by an Administrator (an Administrator can open this tab via “View as”).</span>}
      </div>
      <DataTable data={rows} columns={columns} rowKey={(x) => x.id} pageSize={10}
        searchKeys={(x) => `${x.id} ${x.source} ${x.scope} ${x.reference} ${x.category ?? ""}`} searchPlaceholder="Search factor, source or reference…" />
      <p className="mt-3 text-xs text-muted-foreground">
        For each period the engine applies the factor with the latest “valid from” date on or before the start of that period. Factors cited by
        emission records cannot be edited or deleted; publish a new version instead. Scope 1/2 factors must use one of the platform’s sources and units;
        Scope 3 factors can be any name and unit (e.g. kgCO₂e/INR for spend-based, kgCO₂e/passenger-km for activity-based).
      </p>

      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{dlg?.mode === "new" ? "Add emission factor" : dlg?.mode === "version" ? `New version of ${dlg.factor?.id}` : `Edit ${dlg?.factor?.id}`}</DialogTitle>
            <DialogDescription>
              {frozen ? "This factor is cited by emission records, so only its reference and status can change. Use “New version” to change the value." : "Values are applied from the “valid from” date; earlier periods keep the version that was effective then."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label htmlFor="fa-src">Source / activity name</Label><Input id="fa-src" value={f.source} disabled={frozen || dlg?.mode === "version"} onChange={(e) => set("source", e.target.value)} /></div>
            <div>
              <Label>Scope</Label>
              <Select value={f.scope} disabled={frozen || dlg?.mode === "version"} onValueChange={(v) => set("scope", v as EmissionFactorInput["scope"])}>
                <SelectTrigger aria-label="Scope"><SelectValue /></SelectTrigger>
                <SelectContent>{["Scope 1", "Scope 2", "Scope 3"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Status</Label>
              <Select value={f.status} onValueChange={(v) => set("status", v as "Active" | "Superseded")}>
                <SelectTrigger aria-label="Status"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="Active">Active</SelectItem><SelectItem value="Superseded">Superseded</SelectItem></SelectContent>
              </Select>
            </div>
            {f.scope === "Scope 3" && (
              <div className="col-span-2">
                <Label>Scope 3 category</Label>
                <Select value={f.category || "none"} disabled={frozen || dlg?.mode === "version"} onValueChange={(v) => set("category", v === "none" ? "" : v)}>
                  <SelectTrigger aria-label="Scope 3 category"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Any category</SelectItem>
                    {categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div><Label htmlFor="fa-val">Factor value</Label><Input id="fa-val" type="number" step="any" value={f.value || ""} disabled={frozen} onChange={(e) => set("value", Number(e.target.value))} /></div>
            <div><Label htmlFor="fa-unit">Unit</Label><Input id="fa-unit" placeholder="kgCO₂e/INR" value={f.unit} disabled={frozen} onChange={(e) => set("unit", e.target.value)} /></div>
            <div className="col-span-2"><Label htmlFor="fa-ref">Reference (publication, table, year)</Label><Input id="fa-ref" value={f.reference} onChange={(e) => set("reference", e.target.value)} /></div>
            <div><Label htmlFor="fa-from">Valid from</Label><Input id="fa-from" type="date" value={f.validFrom} disabled={frozen} onChange={(e) => set("validFrom", e.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(null)}>Cancel</Button>
            <Button onClick={save} disabled={create.isPending || update.isPending}>Save factor</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
