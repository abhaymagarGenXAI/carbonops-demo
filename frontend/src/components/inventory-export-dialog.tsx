import { useState } from "react";
import { FileSpreadsheet, FileText, Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useInventoryPreview } from "@/hooks/useApi";
import { reportsApi } from "@/services/entities";
import { useStore } from "@/lib/store";
import type { InventoryQuery } from "@/types/domain";

const fmt = (n: number) => n.toLocaleString("en-IN", { maximumFractionDigits: 2 });

export function InventoryExportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { reportingPeriods, facilities } = useStore();
  const months = reportingPeriods.map((p) => p.period);
  const [from, setFrom] = useState("all");
  const [to, setTo] = useState("all");
  const [basis, setBasis] = useState<"approved" | "pending">("approved");
  const [facility, setFacility] = useState("all");
  const [busy, setBusy] = useState<string | null>(null);
  const q: InventoryQuery = { from, to, basis, facilityId: facility };
  const { data, isLoading, error } = useInventoryPreview(q, open);

  const run = async (kind: "xlsx" | "pdf" | "csv") => {
    setBusy(kind);
    try {
      await reportsApi.download(kind, q);
      toast.success("Inventory exported", { description: `${kind.toUpperCase()} downloaded — the export is recorded in the audit trail.` });
    } catch (e) {
      toast.error("Export failed", { description: e instanceof Error ? e.message : "Unexpected error" });
    } finally {
      setBusy(null);
    }
  };

  const t = data?.summary.totals;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Export GHG inventory</DialogTitle>
          <DialogDescription>Built from the calculation ledger. Every total equals the sum of the record-level trace included in the Excel and CSV files.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          <Select value={from} onValueChange={setFrom}>
            <SelectTrigger className="h-9 w-36" aria-label="From month"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">From: first</SelectItem>{months.map((m) => <SelectItem key={m} value={m}>From {m}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={to} onValueChange={setTo}>
            <SelectTrigger className="h-9 w-36" aria-label="To month"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">To: latest</SelectItem>{months.map((m) => <SelectItem key={m} value={m}>To {m}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={facility} onValueChange={setFacility}>
            <SelectTrigger className="h-9 w-48" aria-label="Facility"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">All facilities</SelectItem>{facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={basis} onValueChange={(v) => setBasis(v as "approved" | "pending")}>
            <SelectTrigger className="h-9 w-56" aria-label="Basis"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="approved">Approved records only</SelectItem>
              <SelectItem value="pending">Approved + pending review</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="rounded-lg border border-border p-3 text-sm">
          {isLoading ? <p className="text-muted-foreground">Preparing preview…</p> : error ? <p className="text-destructive">{error instanceof Error ? error.message : "Preview failed"}</p> : t ? (
            <>
              <div className="grid grid-cols-4 gap-2 text-center">
                {[["Scope 1", fmt(t.scope1)], ["Scope 2", fmt(t.scope2)], ["Scope 3 (entered categories)", fmt(t.scope3)], ["Total", fmt(t.total)]].map(([k, v]) => (
                  <div key={k}><p className="text-xs text-muted-foreground">{k}</p><p className="font-semibold">{v}</p></div>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">tCO₂e · {data!.summary.coverage.recordCount} calculation records · {data!.summary.byFacility.length} facilities · {data!.summary.byMonth.length} months</p>
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">{data!.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button disabled={!!busy || !t} onClick={() => run("xlsx")}><FileSpreadsheet className="size-4" /> {busy === "xlsx" ? "Preparing…" : "Excel (full workbook)"}</Button>
          <Button variant="outline" disabled={!!busy || !t} onClick={() => run("pdf")}><FileText className="size-4" /> {busy === "pdf" ? "Preparing…" : "PDF report"}</Button>
          <Button variant="outline" disabled={!!busy || !t} onClick={() => run("csv")}><Download className="size-4" /> {busy === "csv" ? "Preparing…" : "CSV (calculation trace)"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
