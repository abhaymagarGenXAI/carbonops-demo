import { useMemo, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/data-table";
import { PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { BulkConfirm } from "@/components/bulk-confirm";
import { runBulk } from "@/lib/bulk";
import { useDeleteDocument, useDocumentRepository } from "@/hooks/useApi";
import { usePageMeta } from "@/hooks/use-page-meta";
import { documentsApi } from "@/services/entities";
import type { DocumentRepositoryRow } from "@/types/domain";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");
const bytes = (n: number) => (n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);
const ATTACH_LABEL = { linked: "Linked", inferred: "Facility + month", none: "Not attached" } as const;

function FileBadge({ d }: { d: DocumentRepositoryRow }) {
  if (d.fileMissing) return <Badge variant="destructive">File missing</Badge>;
  if (d.fileOnDisk) return <Badge variant="secondary">Stored</Badge>;
  return <Badge variant="outline">Metadata only</Badge>;
}

function attachedTo(d: DocumentRepositoryRow): string {
  if (d.attachment === "none") return "Nothing — no submission exists for this facility and month";
  return `${d.submissionId}${d.unit ? ` · ${d.unit}` : ""} (${d.facilityName}, ${d.month})`;
}

export default function DocumentsPage() {
  usePageMeta("Document repository — CarbonOps AI", "Every evidence document, where it is attached and the state of its stored file.");
  const { data, isLoading, error } = useDocumentRepository();
  const del = useDeleteDocument();
  const [type, setType] = useState("all");
  const [attach, setAttach] = useState("all");
  const [open, setOpen] = useState<DocumentRepositoryRow | null>(null);
  const [toDelete, setToDelete] = useState<DocumentRepositoryRow | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulkDelete, setBulkDelete] = useState(false);

  const items = data?.items ?? [];
  const types = useMemo(() => Object.keys(data?.summary.byType ?? {}).sort(), [data]);
  const rows = items.filter((d) => (type === "all" || d.type === type) && (attach === "all" || d.attachment === attach));

  const download = async (d: DocumentRepositoryRow) => {
    try { await documentsApi.download(d); } catch (e) { toast.error(msg(e)); }
  };
  const remove = async () => {
    if (!toDelete) return;
    try {
      await del.mutateAsync(toDelete.id);
      toast.success(`Deleted ${toDelete.name}`);
      setOpen(null);
    } catch (e) { toast.error(msg(e)); }
    setToDelete(null);
  };

  const columns: Column<DocumentRepositoryRow>[] = [
    { key: "name", header: "Document", sortable: true, value: (d) => d.name, render: (d) => <div><p className="font-medium">{d.name}</p><p className="text-xs text-muted-foreground">{d.id} · {d.format}</p></div> },
    { key: "type", header: "Type", sortable: true, value: (d) => d.type },
    { key: "facility", header: "Facility", sortable: true, value: (d) => d.facilityName },
    { key: "month", header: "Month", sortable: true, value: (d) => d.month },
    {
      key: "attached", header: "Attached to", value: (d) => d.submissionId ?? "",
      render: (d) => d.attachment === "none"
        ? <Badge variant="outline">Not attached</Badge>
        : <div><p className="text-sm">{d.submissionId}</p><p className="text-xs text-muted-foreground">{ATTACH_LABEL[d.attachment]}{d.submissionStatus ? <> · <StatusBadge value={d.submissionStatus} /></> : null}</p></div>,
    },
    { key: "file", header: "File", render: (d) => <FileBadge d={d} /> },
    { key: "uploadedBy", header: "Uploaded by", sortable: true, value: (d) => d.uploadedBy, render: (d) => <div><p className="text-sm">{d.uploadedBy}</p><p className="text-xs text-muted-foreground">{d.uploadedAt?.slice(0, 10)}</p></div> },
    { key: "size", header: "Size", align: "right", value: (d) => d.sizeBytes ?? 0, sortable: true, render: (d) => <span className="tabular">{d.size}</span> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Document repository" breadcrumb="Governance" description="Every evidence document in the system, where it is attached (the submission it supports) and whether its file is stored. Legacy records created before file storage are metadata only." />
      {error ? <p className="text-sm text-destructive" role="alert">{msg(error)}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Documents" value={data?.summary.total ?? 0} hint={`${bytes(data?.summary.totalBytes ?? 0)} stored`} />
        <StatCard label="Stored files" value={data?.summary.withFile ?? 0} hint={`${data?.summary.metadataOnly ?? 0} metadata-only legacy records`} tone="info" />
        <StatCard label="Not attached" value={data?.summary.unattached ?? 0} hint="No submission for the facility and month" tone="warning" />
        <StatCard label="Missing files" value={data?.summary.missingFiles ?? 0} hint="Recorded but absent from storage" tone="destructive" />
      </div>
      <SectionCard title="All documents" description={`${rows.length} of ${items.length} shown, newest first.`}>
        <DataTable
          data={rows} columns={columns} rowKey={(d) => d.id} pageSize={10} loading={isLoading}
          onRowClick={setOpen}
          selection={{ selected: picked, onChange: setPicked, actions: <Button size="sm" variant="outline" className="text-destructive" onClick={() => setBulkDelete(true)}><Trash2 className="size-4" /> Delete selected</Button> }}
          searchKeys={(d) => `${d.name} ${d.id} ${d.type} ${d.facilityName} ${d.month} ${d.submissionId ?? ""} ${d.uploadedBy}`}
          searchPlaceholder="Search name, facility, submission, uploader…"
          toolbar={
            <div className="flex flex-wrap gap-2">
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="h-9 w-44" aria-label="Document type"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="all">All types</SelectItem>{types.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={attach} onValueChange={setAttach}>
                <SelectTrigger className="h-9 w-44" aria-label="Attachment"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any attachment</SelectItem>
                  <SelectItem value="linked">Linked</SelectItem>
                  <SelectItem value="inferred">Facility + month</SelectItem>
                  <SelectItem value="none">Not attached</SelectItem>
                </SelectContent>
              </Select>
            </div>
          }
        />
      </SectionCard>

      <BulkConfirm
        open={bulkDelete} title={`Delete ${picked.size} document(s)?`} confirmLabel="Delete"
        description="The selected documents and their stored files are removed and cannot be recovered. Evidence of an approved submission is refused and reported."
        onCancel={() => setBulkDelete(false)}
        onConfirm={async () => {
          const { failed } = await runBulk([...picked], "document(s) deleted", (id) => del.mutateAsync(id));
          setPicked(new Set(failed.map((f) => f.id)));
          setBulkDelete(false);
        }}
      />
      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          {open ? (
            <>
              <SheetHeader>
                <SheetTitle className="break-words">{open.name}</SheetTitle>
                <SheetDescription>{open.id} · {open.type} · {open.format}</SheetDescription>
              </SheetHeader>
              <dl className="mt-4 space-y-3 text-sm">
                {([
                  ["Attached to", attachedTo(open)],
                  ["Attachment", ATTACH_LABEL[open.attachment]],
                  ["Submission status", open.submissionStatus ?? "—"],
                  ["Reporting period", `${open.month}${open.periodStatus ? ` (${open.periodStatus})` : ""}`],
                  ["Facility", open.facilityName],
                  ["Uploaded", `${open.uploadedBy} · ${open.uploadedAt?.slice(0, 16).replace("T", " ")}`],
                  ["Size", open.sizeBytes ? bytes(open.sizeBytes) : "—"],
                  ["SHA-256", open.sha256 ?? "—"],
                  ["Version", open.version],
                ] as const).map(([k, v]) => (
                  <div key={k}><dt className="text-xs text-muted-foreground">{k}</dt><dd className="break-all">{v}</dd></div>
                ))}
                <div><dt className="text-xs text-muted-foreground">File</dt><dd><FileBadge d={open} /></dd></div>
                <div>
                  <dt className="text-xs text-muted-foreground">Version history</dt>
                  <dd><ul className="mt-1 space-y-1">{open.versions.map((v) => <li key={v.version} className="text-xs">{v.version} · {v.at?.slice(0, 10)} · {v.by}{v.note ? ` — ${v.note}` : ""}</li>)}</ul></dd>
                </div>
              </dl>
              <div className="mt-6 flex gap-2">
                <Button variant="outline" disabled={!open.fileOnDisk} onClick={() => void download(open)}><Download className="size-4" /> Download</Button>
                <Button variant="outline" className="text-destructive" onClick={() => setToDelete(open)}><Trash2 className="size-4" /> Delete</Button>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>“{toDelete?.name}” and its stored file will be removed and cannot be recovered. Approved evidence cannot be deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); void remove(); }}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
