import { useRef, useState } from "react";
import { Download, Paperclip, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionCard } from "@/components/page-parts";
import { useDeleteDocument, useUploadDocument } from "@/hooks/useApi";
import { documentsApi } from "@/services/entities";
import { useStore } from "@/lib/store";
import { useAuth } from "@/context/AuthContext";
import type { DocumentRec } from "@/types/domain";

export const EVIDENCE_TYPES = [
  "Fuel Bills", "Electricity Bills", "Calibration Reports", "Inspection Reports",
  "Emission Certificates", "Environmental Documents", "Supporting Spreadsheets",
] as const;

/** Evidence files for one facility + month: real uploads on the server, downloadable by anyone who can see the record. */
export function EvidencePanel({ facilityId, month, canUpload, canRemove = canUpload }: { facilityId: string; month: string; canUpload: boolean; canRemove?: boolean }) {
  const { documents, submissions, facilityName } = useStore();
  const upload = useUploadDocument();
  const remove = useDeleteDocument();
  const { user } = useAuth();
  const me = user?.name;
  const reviewer = user?.appRole === "Sustainability Manager" || user?.appRole === "Administrator";
  const input = useRef<HTMLInputElement>(null);
  const [type, setType] = useState<string>(EVIDENCE_TYPES[0]);
  const docs = documents.filter((d) => d.facilityId === facilityId && d.month === month);
  const sub = submissions.find((s) => s.facilityId === facilityId && s.month === month);
  const linked = sub?.id;
  const locked = sub?.status === "Approved"; // approved submissions keep their evidence

  const onPick = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    try {
      const d = await upload.mutateAsync({ file, type, facilityId, month, ...(linked ? { linkedRecord: linked } : {}) });
      toast.success("Evidence uploaded", { description: `${d.name} · ${d.size}` });
    } catch (error) {
      toast.error("Upload failed", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const onRemove = async (d: DocumentRec) => {
    if (!window.confirm(`Remove "${d.name}" from ${facilityName(facilityId)} · ${month}? This deletes the stored file.`)) return;
    try {
      await remove.mutateAsync(d.id);
      toast.success("Evidence removed", { description: d.name });
    } catch (error) {
      toast.error("Could not remove file", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  const download = async (d: DocumentRec) => {
    try {
      await documentsApi.download(d);
    } catch (error) {
      toast.error("Download failed", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  return (
    <SectionCard title="Evidence files" description={`${facilityName(facilityId)} · ${month} · ${docs.length} file(s) · PDF, XLSX, CSV or DOCX, up to 20 MB`}>
      {canUpload && (
        <div className="mb-3 flex gap-2">
          <Select value={type} onValueChange={setType}>
            <SelectTrigger className="min-w-0 flex-1" aria-label="Evidence type"><SelectValue /></SelectTrigger>
            <SelectContent>{EVIDENCE_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
          </Select>
          <input ref={input} type="file" hidden accept=".pdf,.xlsx,.csv,.docx" data-testid="evidence-input" onChange={(e) => onPick(e.target.files?.[0])} />
          <Button type="button" variant="outline" disabled={upload.isPending} onClick={() => input.current?.click()}>
            <Paperclip className="size-4" /> {upload.isPending ? "Uploading…" : "Attach"}
          </Button>
        </div>
      )}
      {docs.length === 0 ? (
        <p className="text-xs text-muted-foreground">No evidence uploaded for this facility and month.</p>
      ) : (
        <ul className="space-y-2.5">
          {docs.map((d) => (
            <li key={d.id} className="flex items-start gap-2.5">
              <Paperclip className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{d.name}</p>
                <p className="text-xs text-muted-foreground">
                  {d.type} · {d.size} · {d.uploadedBy} · {d.uploadedAt}{d.hasFile ? "" : " · metadata only (no stored file)"}
                </p>
              </div>
              {d.hasFile && (
                <Button type="button" size="icon" variant="ghost" aria-label={`Download ${d.name}`} onClick={() => download(d)}>
                  <Download className="size-4" />
                </Button>
              )}
              {canRemove && !locked && (reviewer || d.uploadedBy === me) && (
                <Button type="button" size="icon" variant="ghost" aria-label={`Remove ${d.name}`} disabled={remove.isPending} onClick={() => onRemove(d)}>
                  <Trash2 className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
