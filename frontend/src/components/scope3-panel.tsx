import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DataTable, type Column } from "@/components/data-table";
import { EmptyState, Field, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { BulkConfirm } from "@/components/bulk-confirm";
import { runBulk } from "@/lib/bulk";
import { useAuth } from "@/context/AuthContext";
import { useCreateScope3, useDeleteScope3, useReviewScope3, useScope3, useScope3Categories, useUpdateScope3 } from "@/hooks/useApi";
import { useStore } from "@/lib/store";
import type { Scope3Entry, Scope3Input } from "@/types/domain";

const fmt = (n: number, d = 2) => n.toLocaleString("en-IN", { maximumFractionDigits: d });
const msg = (e: unknown) => (e instanceof Error ? e.message : "Unexpected error");
const unitOf = (u: string) => u.split("/")[1] ?? u;

/** Scope 3 entries: spend- or activity-based, calculated on the server from the versioned factor effective for the month.
 *  Entered by engineers/managers, approved by a different manager; only approved entries reach the inventory. */
export function Scope3Panel() {
  const { user } = useAuth();
  const { factors, facilities, reportingPeriods } = useStore();
  const { can } = useAuth();
  const isManager = can("scope3.approve"); // may approve/reject and change anyone's entry
  const { data: entries = [], isLoading } = useScope3();
  const { data: categories = [] } = useScope3Categories();
  const create = useCreateScope3(), update = useUpdateScope3(), remove = useDeleteScope3(), review = useReviewScope3();

  const openMonths = reportingPeriods.filter((p) => p.status !== "Locked").map((p) => p.period).reverse();
  const s3Factors = factors.filter((f) => f.scope === "Scope 3");
  const blank: Scope3Input = { month: openMonths[0] ?? "", category: "", source: "", activityValue: 0, facilityId: null, description: "" };
  const [dlg, setDlg] = useState<{ id?: string | undefined } | null>(null);
  const [form, setForm] = useState<Scope3Input>(blank);
  const [detail, setDetail] = useState<Scope3Entry | null>(null);
  const [decision, setDecision] = useState<{ entry: Scope3Entry; kind: "Approve" | "Reject" } | null>(null);
  const [comment, setComment] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<"Approve" | "Reject" | "Delete" | null>(null);

  const sources = useMemo(
    () => [...new Map(s3Factors.filter((f) => !form.category || !f.category || f.category === form.category).map((f) => [f.source, f])).values()],
    [s3Factors, form.category],
  );
  const chosen = sources.find((f) => f.source === form.source);

  const approved = entries.filter((e) => e.status === "Approved");
  const byCategory = useMemo(() => {
    const m = new Map<string, number>();
    approved.forEach((e) => m.set(e.category, (m.get(e.category) ?? 0) + e.co2e));
    return [...m].map(([category, value]) => ({ category: category.replace(/^(\d+) .*/, "Cat $1"), full: category, value: Math.round(value * 100) / 100 })).sort((a, b) => b.value - a.value);
  }, [approved]);
  const totalApproved = approved.reduce((a, e) => a + e.co2e, 0);
  const pending = entries.filter((e) => e.status === "Submitted");

  const openDlg = (e?: Scope3Entry) => {
    setForm(e ? { month: e.month, category: e.category, source: e.source, activityValue: e.activityValue, facilityId: e.facilityId, description: e.description } : blank);
    setDlg({ id: e?.id });
  };
  const save = async () => {
    if (!form.month || !form.category || !form.source || !(form.activityValue > 0)) { toast.error("Month, category, emission factor and an activity value above zero are required"); return; }
    try {
      const out = dlg?.id ? await update.mutateAsync({ id: dlg.id, body: form }) : await create.mutateAsync(form);
      toast.success(`${out.id} ${dlg?.id ? "resubmitted" : "submitted"}`, { description: `${fmt(out.co2e)} tCO₂e — ${out.formula}` });
      setDlg(null);
    } catch (e) { toast.error("Could not save the entry", { description: msg(e) }); }
  };
  const decide = async () => {
    if (!decision) return;
    if (decision.kind === "Reject" && !comment.trim()) { toast.error("A comment is required when rejecting"); return; }
    try {
      await review.mutateAsync({ id: decision.entry.id, decision: decision.kind, comment });
      toast.success(`${decision.entry.id} ${decision.kind === "Approve" ? "approved" : "rejected"}`);
      setDecision(null); setComment("");
    } catch (e) { toast.error("Could not record the decision", { description: msg(e) }); }
  };
  const del = (e: Scope3Entry) => remove.mutateAsync(e.id).then(() => toast.success(`${e.id} deleted`)).catch((x: unknown) => toast.error("Could not delete", { description: msg(x) }));

  const canChange = (e: Scope3Entry) => e.status !== "Approved" && (isManager || e.createdById === user?.id);
  const columns: Column<Scope3Entry>[] = [
    { key: "id", header: "Entry", value: (e) => e.id, sortable: true },
    { key: "month", header: "Month", value: (e) => e.month, sortable: true },
    { key: "category", header: "Category", value: (e) => e.category, sortable: true },
    { key: "source", header: "Factor / activity", value: (e) => e.source, render: (e) => <span>{e.source}<span className="block text-xs text-muted-foreground">{e.method}</span></span> },
    { key: "activity", header: "Activity", align: "right", value: (e) => e.activityValue, render: (e) => <span className="tabular">{fmt(e.activityValue, 2)} <span className="text-muted-foreground">{e.unit}</span></span> },
    { key: "co2e", header: "tCO₂e", align: "right", sortable: true, value: (e) => e.co2e, render: (e) => <span className="tabular font-medium">{fmt(e.co2e)}</span> },
    { key: "status", header: "Status", value: (e) => e.status, render: (e) => <StatusBadge value={e.status} /> },
    {
      key: "actions", header: "", render: (e) => (
        <div className="flex justify-end gap-1" onClick={(ev) => ev.stopPropagation()}>
          {isManager && e.status === "Submitted" && e.createdById !== user?.id && (<>
            <Button size="sm" variant="outline" onClick={() => { setComment(""); setDecision({ entry: e, kind: "Approve" }); }}><Check className="size-4" /> Approve</Button>
            <Button size="sm" variant="outline" onClick={() => { setComment(""); setDecision({ entry: e, kind: "Reject" }); }}><X className="size-4" /> Reject</Button>
          </>)}
          {canChange(e) && (<>
            <Button size="icon" variant="ghost" aria-label={`${e.status === "Rejected" ? "Correct" : "Edit"} ${e.id}`} onClick={() => openDlg(e)}><Pencil className="size-4" /></Button>
            <Button size="icon" variant="ghost" aria-label={`Delete ${e.id}`} onClick={() => del(e)}><Trash2 className="size-4" /></Button>
          </>)}
        </div>
      ),
    },
  ];
  const rows = entries.filter((e) => statusFilter === "all" || e.status === statusFilter);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Scope 3 — approved" value={`${fmt(totalApproved)} tCO₂e`} hint={`${approved.length} approved entr${approved.length === 1 ? "y" : "ies"}, ${byCategory.length} categor${byCategory.length === 1 ? "y" : "ies"}`} />
        <StatCard label="Awaiting approval" value={pending.length} hint="Not counted until approved by a different manager" />
        <StatCard label="Scope 3 factors available" value={s3Factors.length} hint={s3Factors.length ? "Maintained under Emission factors" : "Add one under Emission factors first"} />
      </div>

      <SectionCard title="Approved Scope 3 by category" description="tCO₂e, approved entries only. Categories with no entries are not estimated — this is a partial value-chain figure, and is labelled as such in the inventory export.">
        {byCategory.length === 0 ? (
          <EmptyState title="No approved Scope 3 entries yet" hint="Add an entry, then have a different Sustainability Manager approve it." />
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byCategory} margin={{ left: 8, right: 8, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="category" tick={{ fontSize: 11 }} label={{ value: "GHG Protocol category", position: "insideBottom", offset: -10, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: "tCO₂e", angle: -90, position: "insideLeft", fontSize: 11 }} />
                <RTooltip formatter={(v: number) => [`${fmt(v)} tCO₂e`, "Approved"]} labelFormatter={(_, p) => p?.[0]?.payload?.full ?? ""} />
                <Bar dataKey="value" fill="var(--chart-3)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="h-8 w-40" aria-label="Status filter"><SelectValue /></SelectTrigger>
          <SelectContent>{["all", "Submitted", "Approved", "Rejected"].map((s) => <SelectItem key={s} value={s}>{s === "all" ? "All statuses" : s}</SelectItem>)}</SelectContent>
        </Select>
        <Button size="sm" className="ml-auto" onClick={() => openDlg()} disabled={!openMonths.length}><Plus className="size-4" /> Add Scope 3 entry</Button>
      </div>
      {isLoading ? <p className="text-sm text-muted-foreground">Loading…</p> : (
        <DataTable data={rows} columns={columns} rowKey={(e) => e.id} pageSize={10} onRowClick={setDetail}
          selection={{
            selected: picked, onChange: setPicked,
            isSelectable: (e) => canChange(e) || (isManager && e.status === "Submitted" && e.createdById !== user?.id),
            actions: (
              <>
                {isManager ? <Button size="sm" onClick={() => setBulk("Approve")}><Check className="size-4" /> Approve</Button> : null}
                {isManager ? <Button size="sm" variant="outline" onClick={() => setBulk("Reject")}><X className="size-4" /> Reject</Button> : null}
                <Button size="sm" variant="outline" className="text-destructive" onClick={() => setBulk("Delete")}><Trash2 className="size-4" /> Delete</Button>
              </>
            ),
          }}
          searchKeys={(e) => `${e.id} ${e.category} ${e.source} ${e.description} ${e.createdBy}`} searchPlaceholder="Search entry, category or factor…" />
      )}

      <BulkConfirm
        open={bulk !== null} confirmLabel={bulk ?? ""} comment={bulk === "Reject"} requireComment={bulk === "Reject"}
        title={`${bulk} ${picked.size} entr${picked.size === 1 ? "y" : "ies"}?`}
        description={bulk === "Delete" ? "Approved entries and entries you may not change are refused and reported." : bulk === "Approve" ? "Only submitted entries by other people can be approved; the rest are reported. Approved entries are final." : "Each selected entry returns to its author with this reason."}
        onCancel={() => setBulk(null)}
        onConfirm={async (note) => {
          const act = bulk!;
          const { failed } = await runBulk([...picked], act === "Delete" ? "entr(ies) deleted" : act === "Approve" ? "entr(ies) approved" : "entr(ies) rejected",
            (id) => (act === "Delete" ? remove.mutateAsync(id) : review.mutateAsync({ id, decision: act, comment: note })));
          setPicked(new Set(failed.map((f) => f.id)));
          setBulk(null);
        }}
      />

      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{dlg?.id ? `Correct ${dlg.id}` : "Add Scope 3 entry"}</DialogTitle>
            <DialogDescription>The emission is calculated on the server as activity × the factor effective for the month; saving (re)submits it for approval.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Reporting month</Label>
              <Select value={form.month} onValueChange={(v) => setForm({ ...form, month: v })}>
                <SelectTrigger aria-label="Reporting month"><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>{openMonths.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Facility (optional)</Label>
              <Select value={form.facilityId ?? "none"} onValueChange={(v) => setForm({ ...form, facilityId: v === "none" ? null : v })}>
                <SelectTrigger aria-label="Facility"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Corporate / not facility-specific</SelectItem>
                  {facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Scope 3 category</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v, source: "" })}>
                <SelectTrigger aria-label="Scope 3 category"><SelectValue placeholder="Select category" /></SelectTrigger>
                <SelectContent>{categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Emission factor (activity or spend basis)</Label>
              <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
                <SelectTrigger aria-label="Emission factor"><SelectValue placeholder={sources.length ? "Select factor" : "No Scope 3 factor for this category"} /></SelectTrigger>
                <SelectContent>{sources.map((f) => <SelectItem key={f.id} value={f.source}>{f.source} — {f.value} {f.unit}</SelectItem>)}</SelectContent>
              </Select>
              {!sources.length && <p className="mt-1 text-xs text-muted-foreground">An Administrator adds Scope 3 factors under the Emission factors tab.</p>}
            </div>
            <div className="col-span-2">
              <Label htmlFor="s3-act">Activity value{chosen ? ` (${unitOf(chosen.unit)})` : ""}</Label>
              <Input id="s3-act" type="number" step="any" min="0" value={form.activityValue || ""} onChange={(e) => setForm({ ...form, activityValue: Number(e.target.value) })} />
            </div>
            <div className="col-span-2">
              <Label htmlFor="s3-desc">Description / source of data</Label>
              <Textarea id="s3-desc" rows={2} maxLength={300} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(null)}>Cancel</Button>
            <Button onClick={save} disabled={create.isPending || update.isPending}>{dlg?.id ? "Resubmit" : "Submit for approval"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!decision} onOpenChange={(o) => !o && setDecision(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{decision?.kind} {decision?.entry.id}?</DialogTitle>
            <DialogDescription>{decision?.entry.category} · {decision?.entry.month} · {fmt(decision?.entry.co2e ?? 0)} tCO₂e</DialogDescription>
          </DialogHeader>
          <Label htmlFor="s3-cmt">Comment{decision?.kind === "Reject" ? " (required)" : " (optional)"}</Label>
          <Textarea id="s3-cmt" rows={3} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecision(null)}>Cancel</Button>
            <Button onClick={decide} disabled={review.isPending}>{decision?.kind}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{detail?.id} — calculation trace</DialogTitle><DialogDescription>{detail?.category}</DialogDescription></DialogHeader>
          {detail && (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Month" value={detail.month} />
              <Field label="Facility" value={facilities.find((f) => f.id === detail.facilityId)?.name ?? "Corporate / not facility-specific"} />
              <Field label="Method" value={detail.method} />
              <Field label="Activity" value={`${fmt(detail.activityValue, 4)} ${detail.unit}`} />
              <Field label="Emission factor" value={`${detail.factor} ${detail.factorUnit}`} />
              <Field label="Factor version" value={detail.factorId} />
              <div className="col-span-2"><Field label="Factor reference" value={detail.factorRef} /></div>
              <div className="col-span-2"><Field label="Formula" value={detail.formula} /></div>
              {detail.calcNote && <div className="col-span-2"><Field label="Note" value={detail.calcNote} /></div>}
              <Field label="Entered by" value={detail.createdBy} />
              <Field label="Decision" value={detail.reviewer ? `${detail.status} by ${detail.reviewer}` : detail.status} />
              {detail.description && <div className="col-span-2"><Field label="Description" value={detail.description} /></div>}
              {detail.reviewComment && <div className="col-span-2"><Field label="Reviewer comment" value={detail.reviewComment} /></div>}
            </dl>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
