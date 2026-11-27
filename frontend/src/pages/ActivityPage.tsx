import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Copy, Download, Eye, FileSpreadsheet, MoreHorizontal, Save, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DataTable, type Column } from "@/components/data-table";
import { Field, PageHeader, SectionCard } from "@/components/page-parts";
import { StatusBadge } from "@/components/status-badge";
import { useStore } from "@/lib/store";
import { type ImportRow, type Submission } from "@/types/domain";
import { submissionsApi } from "@/services/entities";
import { EvidencePanel } from "@/components/evidence-panel";
import { ImportDialog } from "@/components/import-dialog";
import { useValidationRules } from "@/hooks/useApi";
import { usePageMeta } from "@/hooks/use-page-meta";

const num = (label: string) =>
  z.coerce.number({ invalid_type_error: `${label} must be a number` }).min(0, `${label} cannot be negative`);

const schema = z.object({
  month: z.string().min(1, "Reporting month is required"),
  facilityId: z.string().min(1, "Facility is required"),
  unit: z.string().min(1, "Production unit is required"),
  productionVolume: num("Production volume"),
  electricity: num("Electricity consumption"),
  diesel: num("Diesel consumption"),
  naturalGas: num("Natural gas consumption"),
  steam: num("Steam consumption"),
  water: num("Water consumption"),
  flareGas: num("Flare gas volume"),
  methaneLeak: num("Methane leakage"),
  renewable: num("Renewable energy"),
  operatingHours: z.coerce.number().min(0).max(744, "Operating hours cannot exceed 744 in a month"),
  remarks: z.string().max(500, "Remarks must be under 500 characters").optional().or(z.literal("")),
  notes: z.string().max(1000, "Supporting notes must be under 1000 characters").optional().or(z.literal("")),
});

type FormValues = z.input<typeof schema>;

type UnitFigures = Omit<z.output<typeof schema>, "month" | "facilityId" | "unit">;
const NUMERIC_KEYS = ["productionVolume", "electricity", "diesel", "naturalGas", "steam", "water", "flareGas", "methaneLeak", "renewable"] as const;
/** New forms start empty (shown as the placeholder 0) so typing never has to delete a leading 0; an empty field counts as 0. */
const blankNumbers = () => Object.fromEntries(NUMERIC_KEYS.map((k) => [k, ""])) as unknown as Pick<FormValues, (typeof NUMERIC_KEYS)[number]>;
const FIGURE_KEYS = [...NUMERIC_KEYS, "operatingHours", "remarks", "notes"] as const;
const pickFigures = (v: Record<string, unknown>) => Object.fromEntries(FIGURE_KEYS.map((k) => [k, v[k]])) as Partial<FormValues>;
/** The figures of every unit on a stored submission (older records have a single unit and no unitData). */
const unitsOf = (s: Pick<Submission, "unit" | "data" | "unitData">) => (s.unitData && s.unitData.length ? s.unitData : [{ unit: s.unit, data: s.data }]);

const numericFields: { name: keyof FormValues; label: string; unit: string }[] = [
  { name: "productionVolume", label: "Production volume", unit: "boe" },
  { name: "electricity", label: "Electricity consumption", unit: "kWh" },
  { name: "diesel", label: "Diesel consumption", unit: "litres" },
  { name: "naturalGas", label: "Natural gas consumption", unit: "SCM" },
  { name: "steam", label: "Steam consumption", unit: "tonnes" },
  { name: "water", label: "Water consumption", unit: "m³" },
  { name: "flareGas", label: "Flare gas volume", unit: "SCM" },
  { name: "methaneLeak", label: "Methane leakage estimate", unit: "kg CH₄" },
  { name: "renewable", label: "Renewable energy generated", unit: "kWh" },
  { name: "operatingHours", label: "Operating hours", unit: "hours" },
];

export default function ActivityPage() {
  usePageMeta("Activity Data Collection — CarbonOps AI", "Monthly activity and consumption data capture for production units: drafts, submissions, bulk upload and reviewer feedback.");
  const { currentPeriod, facilities, allFacilities, facilityName, months, reportingPeriods } = useStore();
  /** Locked periods no longer accept data (the API enforces this too). */
  const enterableMonths = [...reportingPeriods].filter((p) => p.status !== "Locked").map((p) => p.period).reverse();

  const { submissions, saveSubmission, documents, aiAlerts } = useStore();
  const [detail, setDetail] = useState<Submission | null>(null);
  const [tab, setTab] = useState("entry");
  const { data: rules } = useValidationRules();
  const [importOpen, setImportOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [facilityFilter, setFacilityFilter] = useState("all");
  const [fromMonth, setFromMonth] = useState("all");
  const [toMonth, setToMonth] = useState("all");
  const [exporting, setExporting] = useState(false);

  const blankForm = (): FormValues => ({
    month: enterableMonths.includes(currentPeriod) ? currentPeriod : (enterableMonths[0] ?? currentPeriod),
    facilityId: facilities[0]?.id ?? "",
    unit: facilities[0]?.units[0] ?? "",
    ...blankNumbers(), operatingHours: 720, remarks: "", notes: "",
  });
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: blankForm() });

  const facilityId = form.watch("facilityId");
  const watchedMonth = form.watch("month");
  // Revision of the facility+month submission when the form was opened on it; sent back so a concurrent change is refused (409).
  const seenRevision = useRef<Record<string, number>>({});
  useEffect(() => {
    const key = `${facilityId}|${watchedMonth}`;
    const existing = submissions.find((s) => s.facilityId === facilityId && s.month === watchedMonth);
    if (existing && !(key in seenRevision.current)) seenRevision.current[key] = existing.revision;
  }, [facilityId, watchedMonth, submissions]);
  const units = facilities.find((f) => f.id === facilityId)?.units ?? [];

  // A month's submission can hold several production units. The form edits ONE unit at a time (the "Production unit"
  // select); the figures of the other units wait in this buffer, and everything is saved together.
  const [unitBuf, setUnitBuf] = useState<Record<string, Partial<FormValues>>>({});
  const blankFigures = (): Partial<FormValues> => ({ ...blankNumbers(), operatingHours: 720, remarks: "", notes: "" });
  const hasFigures = (f: Partial<FormValues> | undefined) => !!f && NUMERIC_KEYS.some((k) => Number(f[k] || 0) !== 0);
  const watchedAll = form.watch();
  const currentUnit = watchedAll.unit;
  /** Buffer including the unit currently on screen. */
  const withCurrent = (): Record<string, Partial<FormValues>> => ({ ...unitBuf, [form.getValues("unit")]: pickFigures(form.getValues()) });
  const switchUnit = (next: string) => {
    const buf = withCurrent();
    setUnitBuf(buf);
    form.reset({ ...form.getValues(), ...(buf[next] ?? blankFigures()), unit: next } as FormValues);
  };
  /** Loads a stored submission (all its units) into the form. */
  const openSubmission = (s: Pick<Submission, "facilityId" | "month" | "unit" | "data" | "unitData">, base: FormValues = form.getValues()) => {
    const lines = unitsOf(s);
    setUnitBuf(Object.fromEntries(lines.map((l) => [l.unit, pickFigures(l.data as unknown as Record<string, unknown>)])));
    form.reset({ ...base, ...pickFigures(lines[0]!.data as unknown as Record<string, unknown>), month: s.month, facilityId: s.facilityId, unit: lines[0]!.unit } as FormValues);
  };
  const unitTotals = useMemo(() => {
    const buf = { ...unitBuf, [currentUnit]: pickFigures(watchedAll) };
    const filled = Object.entries(buf).filter(([u, f]) => units.includes(u) && (u === currentUnit || hasFigures(f)));
    const sum = (k: (typeof NUMERIC_KEYS)[number]) => filled.reduce((a, [, f]) => a + (Number(f[k]) || 0), 0);
    return { filled: filled.map(([u]) => u), sum };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitBuf, watchedAll, currentUnit, units]);

  // Validation, completeness, id generation, reviewer assignment and the audit entry are now computed by the API.
  const persist = async (values: FormValues, status: "Draft" | "Submitted") => {
    const parsed = schema.parse(values);
    const buf = { ...unitBuf, [parsed.unit]: pickFigures(values as unknown as Record<string, unknown>) };
    const lines = Object.entries(buf)
      .filter(([u, f]) => units.includes(u) && (u === parsed.unit || hasFigures(f)))
      .map(([u, f]) => {
        const p = schema.parse({ ...f, month: parsed.month, facilityId: parsed.facilityId, unit: u }) as UnitFigures;
        return { unit: u, data: { productionVolume: p.productionVolume, electricity: p.electricity, diesel: p.diesel, naturalGas: p.naturalGas, steam: p.steam, water: p.water, flareGas: p.flareGas, methaneLeak: p.methaneLeak, renewable: p.renewable, operatingHours: p.operatingHours, remarks: p.remarks ?? "", notes: p.notes ?? "" } };
      });
    const revKey = `${parsed.facilityId}|${parsed.month}`;
    try {
      const record = await saveSubmission({
        ...(revKey in seenRevision.current ? { revision: seenRevision.current[revKey]! } : {}),
        facilityId: parsed.facilityId,
        month: parsed.month,
        status,
        unitData: lines,
      });
      seenRevision.current[revKey] = record.revision;
      if (status === "Draft") toast.success(`Draft ${record.id} saved`, { description: "Resume any time before period close." });
      else toast.success(`${record.id} submitted for review`, { description: `Routed to reviewer queue · completeness ${record.completeness}%` });
    } catch (error) {
      delete seenRevision.current[revKey]; // pick up the latest revision once the page has refreshed
      toast.error(status === "Draft" ? "Could not save draft" : "Could not submit for review", {
        description: error instanceof Error ? error.message : "Unexpected error",
      });
    }
  };

  const duplicatePrevious = () => {
    const idx = months.indexOf(form.getValues("month"));
    const prevMonth = months[Math.max(0, idx - 1)]!;
    const prev = submissions.find((s) => s.facilityId === facilityId && s.month === prevMonth);
    if (!prev) {
      toast.error("No previous submission found", { description: `Nothing recorded for ${facilityName(facilityId)} in ${prevMonth}.` });
      return;
    }
    openSubmission({ ...prev, month: form.getValues("month") });
    toast.info(`Copied ${prev.id}`, { description: "Values carried forward — review before submitting." });
  };

  /** A single importable row from a file fills the form so it can be reviewed before saving. */
  const loadImportedRow = (row: ImportRow) => {
    if (!row.data || !row.facilityId || !row.unit || !row.month) return;
    openSubmission({ facilityId: row.facilityId, month: row.month, unit: row.unit, data: row.data as never });
    toast.info(`Loaded row ${row.row} from file`, { description: "Review the values, then save or submit." });
  };

  const rows = useMemo(
    () =>
      submissions.filter(
        (s) =>
          (statusFilter === "all" || s.status === statusFilter) &&
          (facilityFilter === "all" || s.facilityId === facilityFilter) &&
          (fromMonth === "all" || s.month >= fromMonth) &&
          (toMonth === "all" || s.month <= toMonth),
      ),
    [submissions, statusFilter, facilityFilter, fromMonth, toMonth],
  );

  const exportExcel = async () => {
    setExporting(true);
    try {
      await submissionsApi.exportHistory({ from: fromMonth, to: toMonth, facilityId: facilityFilter, status: statusFilter });
      toast.success("Submission history exported", { description: "Excel workbook downloaded (uses the filters above)." });
    } catch (error) {
      toast.error("Export failed", { description: error instanceof Error ? error.message : "Unexpected error" });
    } finally {
      setExporting(false);
    }
  };

  const columns: Column<Submission>[] = [
    { key: "id", header: "Submission ID", sortable: true, value: (s) => s.id, render: (s) => <span className="font-medium tabular">{s.id}</span> },
    { key: "facility", header: "Facility", sortable: true, value: (s) => facilityName(s.facilityId), render: (s) => (
      <div>
        <p>{facilityName(s.facilityId)}</p>
        <p className="text-xs text-muted-foreground">{s.unit}</p>
      </div>
    ) },
    { key: "month", header: "Reporting month", sortable: true, value: (s) => s.month },
    { key: "status", header: "Status", sortable: true, value: (s) => s.status, render: (s) => <StatusBadge value={s.status} /> },
    { key: "by", header: "Submitted by", sortable: true, value: (s) => s.submittedBy },
    { key: "updated", header: "Last updated", sortable: true, value: (s) => s.updatedAt },
    { key: "validation", header: "Validation", value: (s) => s.validation, render: (s) => <StatusBadge value={s.validation} /> },
    { key: "evidence", header: "Evidence", value: (s) => documents.filter((d) => d.facilityId === s.facilityId && d.month === s.month).length, render: (s) => {
      const n = documents.filter((d) => d.facilityId === s.facilityId && d.month === s.month).length;
      return <span className="text-xs text-muted-foreground">{n ? `${n} file${n > 1 ? "s" : ""}` : "—"}</span>;
    } },
    { key: "comments", header: "Reviewer comments", value: (s) => s.reviewerComments, render: (s) => (
      <span className="line-clamp-1 block max-w-64 text-xs text-muted-foreground">{s.reviewerComments || "—"}</span>
    ) },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Operations"
        title="Activity Data Collection"
        description="Monthly capture of production, energy and emission-relevant activity data. Submissions feed carbon accounting after reviewer approval."
        actions={
          <>
            <Button variant="outline" onClick={duplicatePrevious}>
              <Copy className="size-4" /> Duplicate previous month
            </Button>
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <FileSpreadsheet className="size-4" /> Import CSV / Excel
            </Button>
          </>
        }
      />

      {aiAlerts.filter((a) => a.kind === "rework" || a.kind === "rejected").map((a) => {
        const target = submissions.find((s) => s.id === a.submissionId);
        return (
          <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4">
            <div className="max-w-3xl">
              <p className="text-sm font-medium">{a.title}</p>
              <p className="text-xs text-muted-foreground">{a.detail}</p>
            </div>
            {target ? (
              <Button
                size="sm"
                onClick={() => {
                  openSubmission(target, blankForm());
                  setTab("entry");
                  toast.info(`Loaded ${target.id} into the entry form`, { description: "Correct the values, then submit again." });
                }}
              >
                Correct and resubmit
              </Button>
            ) : null}
          </div>
        );
      })}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="entry">Data entry</TabsTrigger>
          <TabsTrigger value="history">Submission history</TabsTrigger>
        </TabsList>

        <TabsContent value="entry" className="pt-4">
          <Form {...form}>
            <form className="grid gap-4 lg:grid-cols-3" onSubmit={form.handleSubmit((v) => persist(v, "Submitted"))}>
              <div className="space-y-4 lg:col-span-2">
                <SectionCard title="Reporting context" description="Identify the period and organisational scope of this submission.">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <FormField
                      control={form.control}
                      name="month"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Reporting month</FormLabel>
                          <Select value={field.value} onValueChange={field.onChange}>
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>{enterableMonths.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="facilityId"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Facility</FormLabel>
                          <Select
                            value={field.value}
                            onValueChange={(v) => {
                              field.onChange(v);
                              setUnitBuf({});
                              form.setValue("unit", facilities.find((f) => f.id === v)!.units[0]!);
                            }}
                          >
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>{facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="unit"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Production unit being entered</FormLabel>
                          <Select value={field.value} onValueChange={switchUnit}>
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>{units.map((u) => <SelectItem key={u} value={u}>{u}{u !== currentUnit && hasFigures(unitBuf[u]) ? " ✓ entered" : ""}</SelectItem>)}</SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </SectionCard>

                <SectionCard title="Operational activity data" description={`Figures for ${currentUnit || "the selected unit"} in the selected reporting month. Pick another production unit above to add its figures to the same submission.`}>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {numericFields.map((f) => (
                      <FormField
                        key={f.name}
                        control={form.control}
                        name={f.name}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {f.label} <span className="text-muted-foreground">({f.unit})</span>
                            </FormLabel>
                            <FormControl>
                              <Input type="number" inputMode="decimal" placeholder="0" min={0} {...field} value={String(field.value ?? "")} className="tabular" onFocus={(e) => e.currentTarget.select()} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    ))}
                  </div>
                </SectionCard>

                {units.length > 1 ? (
                  <SectionCard title="Facility total for this submission" description={`Sum of ${unitTotals.filled.length} production unit${unitTotals.filled.length === 1 ? "" : "s"} with figures: ${unitTotals.filled.join(", ")}. Saving or submitting sends all of them together as one facility submission.`}>
                    <dl className="grid gap-3 sm:grid-cols-3">
                      {numericFields.filter((f) => f.name !== "operatingHours").map((f) => (
                        <div key={f.name}>
                          <dt className="text-xs text-muted-foreground">{f.label}</dt>
                          <dd className="tabular text-sm font-medium">{unitTotals.sum(f.name as (typeof NUMERIC_KEYS)[number]).toLocaleString("en-IN")} <span className="text-xs font-normal text-muted-foreground">{f.unit}</span></dd>
                        </div>
                      ))}
                    </dl>
                  </SectionCard>
                ) : null}

                <SectionCard title="Remarks & supporting narrative" description="Context helps reviewers validate anomalies faster.">
                  <div className="grid gap-4">
                    <FormField
                      control={form.control}
                      name="remarks"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Remarks</FormLabel>
                          <FormControl><Textarea rows={3} placeholder="e.g. Turnaround shutdown on 12–18 July reduced gas throughput." {...field} /></FormControl>
                          <FormDescription>Maximum 500 characters.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="notes"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Supporting notes</FormLabel>
                          <FormControl><Textarea rows={3} placeholder="Reference meter calibration certificates, invoice numbers or DCS tags." {...field} /></FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </SectionCard>

                <div className="flex flex-wrap gap-2">
                  <Button type="submit">
                    <Send className="size-4" /> Submit for review
                  </Button>
                  <Button type="button" variant="outline" onClick={() => persist(form.getValues(), "Draft")}>
                    <Save className="size-4" /> Save draft
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => form.reset(blankForm())}>
                    Reset form
                  </Button>
                </div>
              </div>

              <div className="space-y-4">
                <SectionCard title="Bulk import" description="Validated before anything is saved.">
                  <Button type="button" variant="outline" className="w-full justify-start" onClick={() => setImportOpen(true)}>
                    <FileSpreadsheet className="size-4" /> Import CSV / Excel file
                  </Button>
                </SectionCard>

                <EvidencePanel facilityId={facilityId} month={form.watch("month")} canUpload />

                <SectionCard title="Validation guidance" description="Rules applied on submit">
                  <ul className="list-disc space-y-1.5 pl-4 text-xs text-muted-foreground">
                    <li>Operating hours must not exceed 744 for a calendar month.</li>
                    {rules ? (
                      <li>
                        {rules.spikeEnabled ? `A source ${rules.spikePct}% or more away from its ${rules.historyMonths}-month mean is flagged (High at ${rules.highPct}%). ` : ""}
                        {rules.zeroEnabled ? "A zero where earlier months were positive is flagged. " : ""}
                        {rules.limits.filter((l) => l.enabled).map((l) => `${l.field} above ${l.max.toLocaleString("en-IN")}${l.block ? " blocks submission" : " is flagged"}. `).join("")}
                      </li>
                    ) : null}
                    <li>Completeness score is derived from populated quantity fields.</li>
                    <li>Approved submissions lock automatically at period close.</li>
                  </ul>
                </SectionCard>
              </div>
            </form>
          </Form>
          <ImportDialog open={importOpen} onOpenChange={setImportOpen} facilityId={facilityId} month={form.watch("month")} onLoadRow={loadImportedRow} />
        </TabsContent>

        <TabsContent value="history" className="pt-4">
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(s) => s.id}
            pageSize={8}
            onRowClick={setDetail}
            searchKeys={(s) => `${s.id} ${facilityName(s.facilityId)} ${s.month} ${s.submittedBy} ${s.status}`}
            searchPlaceholder="Search submission ID, facility or submitter…"
            toolbar={
              <>
                <Select value={facilityFilter} onValueChange={setFacilityFilter}>
                  <SelectTrigger className="h-9 w-52"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All facilities</SelectItem>
                    {allFacilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.active === false ? `${f.name} (inactive)` : f.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={fromMonth} onValueChange={setFromMonth}>
                  <SelectTrigger className="h-9 w-36" aria-label="From month"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">From: any</SelectItem>
                    {months.map((m) => <SelectItem key={m} value={m}>From {m}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={toMonth} onValueChange={setToMonth}>
                  <SelectTrigger className="h-9 w-36" aria-label="To month"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">To: any</SelectItem>
                    {months.map((m) => <SelectItem key={m} value={m}>To {m}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" disabled={exporting} onClick={exportExcel}>
                  <Download className="size-4" /> {exporting ? "Exporting…" : "Export Excel"}
                </Button>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="h-9 w-44"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    {["Draft", "Submitted", "Under Review", "Approved", "Rejected"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </>
            }
            actions={(s) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="Row actions"><MoreHorizontal className="size-4" /></Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => setDetail(s)}><Eye className="size-4" /> View submission</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      openSubmission(s);
                      toast.info(`Loaded ${s.id} into the entry form`);
                    }}
                  >
                    <Copy className="size-4" /> Load into form
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>
      </Tabs>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>{detail.id}</SheetTitle>
                <SheetDescription>
                  {facilityName(detail.facilityId)} · {detail.unit} · {detail.month}
                </SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Status" value={<StatusBadge value={detail.status} />} />
                  <Field label="Validation" value={<StatusBadge value={detail.validation} />} />
                  <Field label="Submitted by" value={detail.submittedBy} />
                  <Field label="Reviewer" value={detail.reviewer} />
                  <Field label="Last updated" value={detail.updatedAt} />
                  <Field label="Completeness" value={`${detail.completeness}%`} />
                </div>
                {detail.status === "Rejected" || (detail.status === "Under Review" && detail.reviewerComments) ? (
                  <SectionCard title={detail.status === "Rejected" ? "Rejected — correction needed" : "Rework requested"} description={detail.reviewer}>
                    <p className="text-sm text-muted-foreground">{detail.reviewerComments || "No comment recorded."}</p>
                    <Button
                      className="mt-3"
                      size="sm"
                      onClick={() => {
                        openSubmission(detail);
                        setDetail(null);
                        setTab("entry");
                        toast.info(`Loaded ${detail.id} into the entry form`, { description: "Correct the values, then submit again." });
                      }}
                    >
                      Correct and resubmit
                    </Button>
                  </SectionCard>
                ) : null}

                <SectionCard title="Reported quantities" description="As captured for the reporting month">
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    {numericFields.map((f) => (
                      <div key={f.name}>
                        <dt className="text-xs text-muted-foreground">{f.label}</dt>
                        <dd className="tabular font-medium">
                          {(detail.data[f.name as keyof typeof detail.data] as number).toLocaleString("en-IN")} {f.unit}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </SectionCard>
                {(detail.unitData?.length ?? 0) > 1 ? (
                  <SectionCard title="By production unit" description="The facility quantities above are the sum of these units (operating hours: the longest-running unit).">
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead><tr className="text-left text-muted-foreground"><th className="py-1 pr-3 font-medium">Unit</th>{numericFields.filter((f) => f.name !== "operatingHours").map((f) => <th key={f.name} className="px-2 py-1 text-right font-medium">{f.label.split(" ")[0]}</th>)}<th className="px-2 py-1 text-right font-medium">Hours</th></tr></thead>
                        <tbody>
                          {detail.unitData!.map((u) => (
                            <tr key={u.unit} className="border-t border-border">
                              <td className="py-1 pr-3">{u.unit}</td>
                              {numericFields.filter((f) => f.name !== "operatingHours").map((f) => <td key={f.name} className="tabular px-2 py-1 text-right">{(u.data[f.name as keyof typeof u.data] as number).toLocaleString("en-IN")}</td>)}
                              <td className="tabular px-2 py-1 text-right">{u.data.operatingHours}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </SectionCard>
                ) : null}
                {detail.anomalies.length ? (
                  <SectionCard title="Anomaly flags" description="Raised by validation rules">
                    <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
                      {detail.anomalies.map((a) => <li key={a}>{a}</li>)}
                    </ul>
                  </SectionCard>
                ) : null}
                <EvidencePanel facilityId={detail.facilityId} month={detail.month} canUpload={false} canRemove />

                <SectionCard title="Reviewer comments" description={detail.reviewer}>
                  <p className="text-sm text-muted-foreground">{detail.reviewerComments || "No reviewer comments recorded."}</p>
                </SectionCard>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
