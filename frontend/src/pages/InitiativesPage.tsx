import { useMemo, useState } from "react";
import { CheckCircle2, Leaf, Plus, Target, TrendingUp, Wallet } from "lucide-react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/data-table";
import { Field, PageHeader, SectionCard, StatCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useAuth } from "@/context/AuthContext";
import { useStore } from "@/lib/store";
import { type Initiative } from "@/types/domain";
import { InitiativeAnalysis } from "@/components/initiative-analysis";
import { InitiativeEditor } from "@/components/initiative-editor";
import { usePageMeta } from "@/hooks/use-page-meta";

const TYPES = ["Boiler Optimization", "Flare Gas Recovery", "Solar Installation", "Energy Efficiency", "Methane Leak Detection", "Electrification", "Process Optimization"];
const crore = (n: number) => `₹${(n / 10_000_000).toFixed(2)} Cr`;

interface DraftErrors {
  name?: string;
  expectedReduction?: string;
  investment?: string;
}

export default function InitiativesPage() {
  usePageMeta("Decarbonization Initiatives — CarbonOps AI", "Portfolio of emission reduction projects with expected versus actual abatement, investment, ROI and milestone tracking.");
  const { facilities, allFacilities, facilityName } = useStore();
  const { can } = useAuth();

  const { initiatives, createInitiative } = useStore();
  const [detail, setDetail] = useState<Initiative | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("all");
  const [facility, setFacility] = useState("all");
  const [errors, setErrors] = useState<DraftErrors>({});
  const [draft, setDraft] = useState({
    name: "",
    type: TYPES[0]!,
    owner: "",
    facilityId: facilities[0]?.id ?? "",
    expectedReduction: "",
    investment: "",
    annualSavings: "",
    startDate: "2026-09-01",
    endDate: "2027-03-31",
    priority: "High" as Initiative["priority"],
    notes: "",
  });

  const rows = useMemo(
    () =>
      initiatives.filter(
        (i) => (status === "all" || i.status === status) && (facility === "all" || i.facilityId === facility),
      ),
    [initiatives, status, facility],
  );

  const totals = useMemo(() => {
    const expected = initiatives.reduce((a, b) => a + b.expectedReduction, 0);
    const actual = initiatives.reduce((a, b) => a + b.actualReduction, 0);
    const invest = initiatives.reduce((a, b) => a + b.investment, 0);
    const active = initiatives.filter((i) => i.status === "In Progress").length;
    return { expected, actual, invest, active };
  }, [initiatives]);

  const chart = useMemo(
    () =>
      initiatives.slice(0, 8).map((i) => ({
        name: i.name.split("—")[0]!.trim().slice(0, 18),
        Expected: i.expectedReduction,
        Actual: i.actualReduction,
      })),
    [initiatives],
  );

  const save = () => {
    const e: DraftErrors = {};
    if (!draft.name.trim()) e.name = "Initiative name is required";
    else if (draft.name.trim().length > 120) e.name = "Keep the name under 120 characters";
    const red = Number(draft.expectedReduction);
    if (!draft.expectedReduction || Number.isNaN(red) || red <= 0) e.expectedReduction = "Enter an expected reduction greater than zero";
    const inv = Number(draft.investment);
    if (!draft.investment || Number.isNaN(inv) || inv < 0) e.investment = "Enter a valid investment amount";
    setErrors(e);
    if (Object.keys(e).length) return;

    // id, ROI, default milestones and status are computed by the API
    createInitiative({
      name: draft.name.trim(),
      type: draft.type,
      owner: draft.owner.trim() || "Unassigned",
      facilityId: draft.facilityId,
      expectedReduction: red,
      investment: inv,
      annualSavings: Number(draft.annualSavings) || 0,
      startDate: draft.startDate,
      endDate: draft.endDate,
      priority: draft.priority,
      notes: draft.notes.trim(),
    })
      .then((record) => {
        toast.success("Initiative created", { description: `${record.id} added to the abatement portfolio.` });
        setOpen(false);
        setDraft({ ...draft, name: "", owner: "", expectedReduction: "", investment: "", annualSavings: "", notes: "" });
      })
      .catch((error: unknown) => {
        toast.error("Initiative could not be created", { description: error instanceof Error ? error.message : "Unexpected error" });
      });
  };

  const columns: Column<Initiative>[] = [
    { key: "name", header: "Initiative", sortable: true, value: (i) => i.name, render: (i) => (
      <div className="max-w-72">
        <p className="truncate font-medium">{i.name}</p>
        <p className="text-xs text-muted-foreground">{i.id} · {i.type}</p>
      </div>
    ) },
    { key: "facility", header: "Facility", sortable: true, value: (i) => facilityName(i.facilityId) },
    { key: "owner", header: "Owner", sortable: true, value: (i) => i.owner },
    { key: "status", header: "Status", sortable: true, value: (i) => i.status, render: (i) => <StatusBadge value={i.status} /> },
    { key: "expected", header: "Expected tCO₂e/yr", align: "right", sortable: true, value: (i) => i.expectedReduction, render: (i) => <span className="tabular">{i.expectedReduction.toLocaleString("en-IN")}</span> },
    { key: "actual", header: "Actual tCO₂e/yr", align: "right", sortable: true, value: (i) => i.actualReduction, render: (i) => <span className="tabular">{i.actualReduction.toLocaleString("en-IN")}</span> },
    { key: "investment", header: "Investment", align: "right", sortable: true, value: (i) => i.investment, render: (i) => <span className="tabular">{crore(i.investment)}</span> },
    { key: "macc", header: "₹/tCO₂e", align: "right", sortable: true, value: (i) => i.maccCost ?? 0, render: (i) => <span className="tabular" title="Marginal abatement cost: (annualised investment − annual savings) ÷ expected reduction">{i.maccCost == null ? "—" : Math.round(i.maccCost).toLocaleString("en-IN")}</span> },
    { key: "roi", header: "ROI", align: "right", sortable: true, value: (i) => i.roi, render: (i) => <span className="tabular">{i.roi}%</span> },
    { key: "completion", header: "Completion", sortable: true, value: (i) => i.completion, render: (i) => (
      <div className="flex w-32 items-center gap-2">
        <Progress value={i.completion} className="h-1.5" />
        <span className="tabular text-xs text-muted-foreground">{i.completion}%</span>
      </div>
    ) },
    { key: "timeline", header: "Timeline", sortable: true, value: (i) => i.timeline, render: (i) => <StatusBadge value={i.timeline} /> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Carbon"
        title="Decarbonization Initiatives"
        description="Abatement project portfolio — planned versus realised emission reductions, capital deployed and delivery milestones."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" /> New initiative
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Planned abatement" value={`${totals.expected.toLocaleString("en-IN")} tCO₂e`} hint="Annualised across portfolio" icon={<Target className="size-4" />} tone="info" />
        <StatCard label="Realised abatement" value={`${totals.actual.toLocaleString("en-IN")} tCO₂e`} hint={`${totals.expected ? ((totals.actual / totals.expected) * 100).toFixed(0) : 0}% of plan achieved`} icon={<Leaf className="size-4" />} tone="success" />
        <StatCard label="Capital deployed" value={crore(totals.invest)} hint="Approved project investment" icon={<Wallet className="size-4" />} />
        <StatCard label="Active projects" value={totals.active} hint="Currently in execution" icon={<TrendingUp className="size-4" />} tone="warning" />
      </div>

      <Tabs defaultValue="portfolio">
        <TabsList>
          <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="analysis">Analysis &amp; assumptions</TabsTrigger>
        </TabsList>

        <TabsContent value="portfolio" className="pt-4">
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(i) => i.id}
            pageSize={8}
            onRowClick={setDetail}
            searchKeys={(i) => `${i.id} ${i.name} ${i.type} ${i.owner} ${facilityName(i.facilityId)}`}
            searchPlaceholder="Search initiative, owner or type…"
            toolbar={
              <>
                <Select value={facility} onValueChange={setFacility}>
                  <SelectTrigger className="h-9 w-52"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All facilities</SelectItem>
                    {allFacilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.active === false ? `${f.name} (inactive)` : f.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    {["Planned", "In Progress", "On Hold", "Completed"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </>
            }
          />
        </TabsContent>

        <TabsContent value="analysis" className="pt-4">
          <InitiativeAnalysis />
        </TabsContent>

        <TabsContent value="performance" className="pt-4">
          <SectionCard title="Expected versus actual abatement" description="Annualised tCO₂e by initiative">
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} layout="vertical" margin={{ left: 40, bottom: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" stroke="var(--muted-foreground)" fontSize={12} label={{ value: "Reduction (tCO₂e per year)", position: "insideBottom", offset: -12, fontSize: 12, fill: "var(--muted-foreground)" }} />
                  <YAxis type="category" dataKey="name" width={130} stroke="var(--muted-foreground)" fontSize={11} />
                  <RTooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${Number(v).toLocaleString("en-IN")} tCO₂e/yr`, n]} />
                  <Bar dataKey="Expected" fill="var(--chart-3)" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="Actual" fill="var(--chart-2)" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        </TabsContent>
      </Tabs>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>New decarbonization initiative</DialogTitle>
            <DialogDescription>Register an abatement project for portfolio tracking and approval.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="init-name">Initiative name</Label>
              <Input id="init-name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Waste Heat Recovery — Compressor Train B" />
              {errors.name ? <p className="mt-1 text-xs text-destructive">{errors.name}</p> : null}
            </div>
            <div>
              <Label>Initiative type</Label>
              <Select value={draft.type} onValueChange={(v) => setDraft({ ...draft, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Facility</Label>
              <Select value={draft.facilityId} onValueChange={(v) => setDraft({ ...draft, facilityId: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="init-owner">Project owner</Label>
              <Input id="init-owner" value={draft.owner} onChange={(e) => setDraft({ ...draft, owner: e.target.value })} placeholder="e.g. K. Iyer" />
            </div>
            <div>
              <Label>Priority</Label>
              <Select value={draft.priority} onValueChange={(v) => setDraft({ ...draft, priority: v as Initiative["priority"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["Critical", "High", "Medium", "Low"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="init-red">Expected reduction (tCO₂e/yr)</Label>
              <Input id="init-red" type="number" value={draft.expectedReduction} onChange={(e) => setDraft({ ...draft, expectedReduction: e.target.value })} />
              {errors.expectedReduction ? <p className="mt-1 text-xs text-destructive">{errors.expectedReduction}</p> : null}
            </div>
            <div>
              <Label htmlFor="init-inv">Investment (₹)</Label>
              <Input id="init-inv" type="number" value={draft.investment} onChange={(e) => setDraft({ ...draft, investment: e.target.value })} />
              {errors.investment ? <p className="mt-1 text-xs text-destructive">{errors.investment}</p> : null}
            </div>
            <div>
              <Label htmlFor="init-sav">Annual savings (₹/yr, optional)</Label>
              <Input id="init-sav" type="number" value={draft.annualSavings} onChange={(e) => setDraft({ ...draft, annualSavings: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="init-start">Start date</Label>
              <Input id="init-start" type="date" value={draft.startDate} onChange={(e) => setDraft({ ...draft, startDate: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="init-end">Target completion</Label>
              <Input id="init-end" type="date" value={draft.endDate} onChange={(e) => setDraft({ ...draft, endDate: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="init-notes">Notes</Label>
              <Textarea id="init-notes" rows={3} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="Scope, technology, dependencies…" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>Create initiative</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>{detail.name}</SheetTitle>
                <SheetDescription>{detail.id} · {detail.type} · {facilityName(detail.facilityId)}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Status" value={<StatusBadge value={detail.status} />} />
                  <Field label="Timeline" value={<StatusBadge value={detail.timeline} />} />
                  <Field label="Owner" value={detail.owner} />
                  <Field label="Priority" value={detail.priority} />
                  <Field label="Expected reduction" value={`${detail.expectedReduction.toLocaleString("en-IN")} tCO₂e/yr`} />
                  <Field label="Verified reduction (M&V)" value={`${detail.actualReduction.toLocaleString("en-IN")} tCO₂e/yr`} />
                  <Field label="Investment" value={crore(detail.investment)} />
                  <Field label="Annual savings" value={`₹${(detail.annualSavings ?? 0).toLocaleString("en-IN")}`} />
                  <Field label="ROI" value={`${detail.roi}%`} />
                  <Field label="Payback" value={detail.paybackYears == null ? "—" : `${detail.paybackYears} years`} />
                  <Field label="Cost per tCO₂e" value={detail.maccCost == null ? "—" : `₹${Math.round(detail.maccCost).toLocaleString("en-IN")}${detail.maccCost < 0 ? " (saves money)" : ""}`} />
                  <Field label="Start date" value={detail.startDate} />
                  <Field label="Target completion" value={detail.endDate} />
                  <Field label="Dependencies" value={detail.dependencies} />
                </div>

                <SectionCard title="Completion" description={`${detail.completion}% delivered`}>
                  <Progress value={detail.completion} className="h-2" />
                </SectionCard>

                <SectionCard title="Milestones" description={`${detail.milestones.filter((m) => m.done).length} of ${detail.milestones.length} complete`}>
                  <ul className="space-y-3">
                    {detail.milestones.map((m) => (
                      <li key={m.name} className="flex items-start gap-2.5">
                        <CheckCircle2 className={m.done ? "mt-0.5 size-4 text-success" : "mt-0.5 size-4 text-muted-foreground"} />
                        <div>
                          <p className="text-sm">{m.name}</p>
                          <p className="text-xs text-muted-foreground">{m.date}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </SectionCard>

                <SectionCard title="Notes" description="Project context">
                  <p className="text-sm text-muted-foreground">{detail.notes || "No notes recorded."}</p>
                </SectionCard>

                {can("initiative.manage") ? <InitiativeEditor initiative={detail} onSaved={setDetail} /> : null}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
