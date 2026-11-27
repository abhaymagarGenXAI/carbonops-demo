import { useRef, useState } from "react";
import { Download, FileDown, FileSpreadsheet, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { useMasterImport } from "@/hooks/useApi";
import { masterDataApi } from "@/services/entities";
import type { MasterImportReport } from "@/types/domain";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");

/** Export (everyone) and Excel template + upload (permission master.import) for facilities and assets. */
export function MasterDataExcel() {
  const { can } = useAuth();
  const canImport = can("master.import");
  const imp = useMasterImport();
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<MasterImportReport | null>(null);

  const run = (fn: () => Promise<void>) => fn().catch((e) => toast.error(msg(e)));
  const reset = () => { setFile(null); setReport(null); if (input.current) input.current.value = ""; };

  const check = async (f: File) => {
    setFile(f);
    setReport(null);
    try { setReport(await imp.mutateAsync({ file: f, dryRun: true })); } catch (e) { toast.error(msg(e)); }
  };
  const apply = async () => {
    if (!file) return;
    try {
      const r = await imp.mutateAsync({ file, dryRun: false });
      toast.success(`Saved: ${r.summary.Facilities.create + r.summary.Facilities.update} facility row(s), ${r.summary.Assets.create + r.summary.Assets.update} asset row(s)`);
      setOpen(false);
      reset();
    } catch (e) { toast.error(msg(e)); }
  };

  const flagged = report?.rows.filter((r) => r.errors.length || r.warnings.length) ?? [];
  return (
    <>
      <Button variant="outline" onClick={() => void run(masterDataApi.export)}><Download className="size-4" /> Export Excel</Button>
      {canImport ? (
        <>
          <Button variant="outline" onClick={() => void run(masterDataApi.template)}><FileDown className="size-4" /> Template</Button>
          <Button variant="outline" onClick={() => { reset(); setOpen(true); }}><Upload className="size-4" /> Upload Excel</Button>
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
            <DialogContent className="max-w-3xl">
              <DialogHeader>
                <DialogTitle>Upload facilities & assets</DialogTitle>
                <DialogDescription>
                  Use the template (or an export). Facilities are matched by code and assets by Asset ID: existing rows are updated, new ones created, nothing is deleted. The file is checked first; it is saved only if every row is valid.
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-wrap items-center gap-2">
                <input ref={input} type="file" accept=".xlsx" className="hidden" aria-label="Excel file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void check(f); }} />
                <Button variant="secondary" onClick={() => input.current?.click()} disabled={imp.isPending}><FileSpreadsheet className="size-4" /> {file ? "Choose another file" : "Choose .xlsx file"}</Button>
                {file ? <span className="text-sm text-muted-foreground">{file.name}</span> : null}
              </div>
              {imp.isPending && !report ? <p className="text-sm text-muted-foreground">Checking…</p> : null}
              {report ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap gap-2 text-sm">
                    {(["Facilities", "Assets"] as const).map((s) => (
                      <Badge key={s} variant="secondary">{s}: {report.summary[s].create} new · {report.summary[s].update} updated{report.summary[s].error ? ` · ${report.summary[s].error} with errors` : ""}</Badge>
                    ))}
                  </div>
                  {report.canApply ? (
                    <p className="text-sm text-emerald-700 dark:text-emerald-400">All rows are valid. Nothing has been saved yet.</p>
                  ) : (
                    <p className="text-sm text-destructive" role="alert">Fix the rows below and choose the file again. Nothing was saved.</p>
                  )}
                  {flagged.length ? (
                    <div className="max-h-64 overflow-y-auto rounded-md border">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-muted"><tr className="text-left"><th className="px-2 py-1">Sheet</th><th className="px-2 py-1">Row</th><th className="px-2 py-1">Record</th><th className="px-2 py-1">Problem</th></tr></thead>
                        <tbody>
                          {flagged.map((r) => (
                            <tr key={`${r.sheet}-${r.row}`} className="border-t align-top">
                              <td className="px-2 py-1">{r.sheet}</td><td className="px-2 py-1">{r.row}</td><td className="px-2 py-1">{r.key}</td>
                              <td className="px-2 py-1">{r.errors.map((e) => <p key={e} className="text-destructive">{e}</p>)}{r.warnings.map((w) => <p key={w} className="text-amber-700 dark:text-amber-400">{w}</p>)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
                <Button onClick={() => void apply()} disabled={!report?.canApply || imp.isPending}>{imp.isPending && report ? "Saving…" : "Save to database"}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      ) : null}
    </>
  );
}
