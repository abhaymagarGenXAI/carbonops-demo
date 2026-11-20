import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useImportCommit } from "@/hooks/useApi";
import { submissionsApi } from "@/services/entities";
import type { ImportCommitResult, ImportPreview, ImportRow } from "@/types/domain";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** current form selection, used for files that have no facility / month column */
  facilityId: string;
  month: string;
  /** single importable row → fill the entry form so it can be reviewed before saving */
  onLoadRow: (row: ImportRow) => void;
}

const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");

export function ImportDialog({ open, onOpenChange, facilityId, month, onLoadRow }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const commit = useImportCommit();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportCommitResult | null>(null);

  const reset = () => { setPreview(null); setResult(null); };
  const close = (o: boolean) => { if (!o) reset(); onOpenChange(o); };

  const onPick = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      setPreview(await submissionsApi.importPreview(file, { facilityId, month }));
    } catch (e) {
      setPreview(null);
      toast.error("Could not read the file", { description: msg(e) });
    } finally {
      setBusy(false);
    }
  };

  const ready = preview?.rows.filter((r) => r.importable) ?? [];
  const save = async (status: "Draft" | "Submitted") => {
    try {
      const res = await commit.mutateAsync({
        status,
        rows: ready.map((r) => ({ facilityId: r.facilityId!, unit: r.unit!, month: r.month!, data: r.data! })),
      });
      setResult(res);
      setPreview(null);
      const verb = status === "Draft" ? "saved as drafts" : "submitted for review";
      if (res.failed === 0) toast.success(`${res.saved} row(s) ${verb}`);
      else toast.warning(`${res.saved} row(s) ${verb}, ${res.failed} failed`, { description: "See the list for details." });
    } catch (e) {
      toast.error("Import failed", { description: msg(e) });
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import activity data (CSV / Excel)</DialogTitle>
          <DialogDescription>
            One row per facility and month. The file is checked first — nothing is saved until you confirm. Blank values are never treated as zero.
          </DialogDescription>
        </DialogHeader>

        <input ref={input} type="file" hidden accept=".csv,.xlsx" data-testid="import-input" onChange={(e) => onPick(e.target.files?.[0])} />

        {!preview && !result && (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border p-8 text-center">
            <FileSpreadsheet className="size-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Choose a .csv or .xlsx file (max 5 MB, 500 rows). Facility/month columns are optional if you use the form selection ({month}).</p>
            <div className="flex gap-2">
              <Button disabled={busy} onClick={() => input.current?.click()}>{busy ? "Reading…" : "Choose file"}</Button>
              <Button variant="outline" onClick={() => submissionsApi.downloadTemplate().catch((e) => toast.error("Download failed", { description: msg(e) }))}>
                Download template
              </Button>
            </div>
          </div>
        )}

        {preview && (
          <div className="space-y-3 text-sm">
            <p>
              <b>{preview.fileName}</b>{preview.sheet ? ` · sheet “${preview.sheet}”` : ""} — {preview.rowCount} row(s):{" "}
              <span className="text-success">{preview.importableRows} ready</span>
              {preview.errorRows > 0 && <>, <span className="text-destructive">{preview.errorRows} with errors (will be skipped)</span></>}
            </p>
            {preview.unmappedColumns.length > 0 && (
              <p className="text-xs text-muted-foreground">Ignored columns (not recognised): {preview.unmappedColumns.join(", ")}</p>
            )}
            <div className="max-h-72 overflow-auto rounded-md border">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-muted text-left">
                  <tr><th className="p-2">Row</th><th className="p-2">Facility · unit</th><th className="p-2">Month</th><th className="p-2">Result</th></tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.row} className="border-t align-top">
                      <td className="tabular p-2">{r.row}</td>
                      <td className="p-2">{r.facilityName ?? "—"}<br /><span className="text-muted-foreground">{r.unit ?? ""}</span></td>
                      <td className="p-2">{r.month ?? "—"}</td>
                      <td className="space-y-1 p-2">
                        {r.importable && <p className="flex items-center gap-1 text-success"><CheckCircle2 className="size-3.5" /> Ready</p>}
                        {r.errors.map((e) => <p key={e} className="flex items-start gap-1 text-destructive"><XCircle className="mt-0.5 size-3.5 shrink-0" /> {e}</p>)}
                        {r.warnings.map((w) => <p key={w} className="flex items-start gap-1 text-warning-foreground"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {w}</p>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-2 text-sm">
            <p><b>{result.saved}</b> saved{result.failed > 0 && <>, <b className="text-destructive">{result.failed}</b> failed</>}.</p>
            <ul className="max-h-56 space-y-1 overflow-auto text-xs">
              {result.results.map((r, i) => (
                <li key={i} className={r.ok ? "text-success" : "text-destructive"}>
                  {r.ok ? `✓ ${r.submissionId}` : `✗ ${r.facilityId} ${r.month}: ${r.detail}`}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex gap-2">
            {preview && <Button variant="ghost" onClick={reset}>Choose another file</Button>}
          </div>
          <div className="flex flex-wrap gap-2">
            {preview && ready.length === 1 && (
              <Button variant="outline" onClick={() => { onLoadRow(ready[0]!); close(false); }}>Load into form</Button>
            )}
            {preview && (
              <>
                <Button variant="outline" disabled={ready.length === 0 || commit.isPending} onClick={() => save("Draft")}>
                  Save {ready.length} as draft{ready.length === 1 ? "" : "s"}
                </Button>
                <Button disabled={ready.length === 0 || commit.isPending} onClick={() => save("Submitted")}>
                  Submit {ready.length} for review
                </Button>
              </>
            )}
            {result && <Button onClick={() => close(false)}>Done</Button>}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
