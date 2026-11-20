/** Typed REST clients, one per backend resource. All go through the shared Axios instance. */
import type {
  InventoryQuery,
  InventoryReport,
  InitiativeAnalysis,
  InitiativeAssumptions,
  InitiativePatch,
  TargetsView,
  EmissionTarget,
  ValidationRules,
  AiAlert,
  Asset,
  AuditEntry,
  DocumentRec,
  ImportCommitResult,
  ImportPreview,
  EmissionFactor,
  EmissionFactorInput,
  Scope3Entry,
  Scope3Input,
  EmissionRecord,
  EnergyReconcileResult,
  EnergyRecord,
  Facility,
  Initiative,
  InitiativeCreatePayload,
  RecalculateResult,
  ReportingPeriod,
  ReviewDecision,
  Submission,
  SubmissionSavePayload,
  UserRec,
} from "@/types/domain";
import { saveBlob } from "@/lib/csv";
import { api } from "./api";

const data = async <T>(p: Promise<{ data: T }>): Promise<T> => (await p).data;
const enc = encodeURIComponent;

export interface DeleteResult {
  id: string;
  deleted: boolean;
}

export type FacilityInput = Omit<Facility, "createdAt" | "updatedAt">;
export type FacilityChanges = Partial<Omit<FacilityInput, "id">>;
export type AssetChanges = Partial<Omit<Asset, "id">>;

export const facilitiesApi = {
  list: () => data(api.get<Facility[]>("/facilities")),
  create: (body: FacilityInput) => data(api.post<Facility>("/facilities", body)),
  update: (id: string, changes: FacilityChanges) => data(api.patch<Facility>(`/facilities/${enc(id)}`, changes)),
  remove: (id: string) => data(api.delete<DeleteResult>(`/facilities/${enc(id)}`)),
};

export const assetsApi = {
  list: () => data(api.get<Asset[]>("/assets")),
  create: (body: Asset) => data(api.post<Asset>("/assets", body)),
  update: (id: string, changes: AssetChanges) => data(api.patch<Asset>(`/assets/${enc(id)}`, changes)),
  remove: (id: string) => data(api.delete<DeleteResult>(`/assets/${enc(id)}`)),
};

export const submissionsApi = {
  list: () => data(api.get<Submission[]>("/submissions")),
  save: (body: SubmissionSavePayload) => data(api.post<Submission>("/submissions", body)),
  review: (id: string, status: ReviewDecision, comment: string, revision?: number) =>
    data(api.post<Submission>(`/submissions/${enc(id)}/review`, { status, comment, revision })),
  exportHistory: async (q: { from?: string; to?: string; facilityId?: string; status?: string }) => {
    const params = Object.fromEntries(Object.entries(q).filter(([, v]) => v && v !== "all"));
    const res = await api.get<Blob>("/submissions/export", { params, responseType: "blob", timeout: 120_000 });
    const name = /filename="?([^";]+)"?/.exec(String(res.headers["content-disposition"] ?? ""))?.[1] ?? "submission-history.xlsx";
    saveBlob(res.data, name);
  },
  importPreview: (file: File, ctx: { facilityId?: string; month?: string }) => {
    const fd = new FormData();
    fd.append("file", file);
    if (ctx.facilityId) fd.append("facilityId", ctx.facilityId);
    if (ctx.month) fd.append("month", ctx.month);
    return data(api.post<ImportPreview>("/submissions/import/preview", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 }));
  },
  importCommit: (body: { status: "Draft" | "Submitted"; rows: { facilityId: string; unit: string; month: string; data: Record<string, number | string> }[] }) =>
    data(api.post<ImportCommitResult>("/submissions/import", body, { timeout: 120_000 })),
  downloadTemplate: async () => {
    const res = await api.get<Blob>("/submissions/import/template", { responseType: "blob" });
    saveBlob(res.data, "activity-import-template.csv");
  },
};

export interface EnergyEdit {
  meterRef?: string;
  invoiceRef?: string;
  cost?: number;
}
export const energyApi = {
  list: () => data(api.get<EnergyRecord[]>("/energy-records")),
  update: (id: string, changes: EnergyEdit) => data(api.patch<EnergyRecord>(`/energy-records/${enc(id)}`, changes)),
  reconcile: (body: { month?: string | undefined; facilityId?: string | undefined; dryRun: boolean }) =>
    data(api.post<EnergyReconcileResult>("/energy-records/reconcile", body)),
};

export const emissionsApi = {
  list: () => data(api.get<EmissionRecord[]>("/emission-records")),
  review: (id: string, status: ReviewDecision, comment: string) =>
    data(api.post<EmissionRecord>(`/emission-records/${enc(id)}/review`, { status, comment })),
};

export interface RecalculateParams {
  month?: string | undefined;
  facilityId?: string | undefined;
  dryRun: boolean;
}
export const emissionsRecalc = (body: RecalculateParams) =>
  data(api.post<RecalculateResult>("/emission-records/recalculate", body));

export const emissionFactorsApi = {
  list: () => data(api.get<EmissionFactor[]>("/emission-factors")),
  create: (b: EmissionFactorInput) => data(api.post<EmissionFactor>("/emission-factors", b)),
  update: (id: string, b: Partial<EmissionFactorInput>) => data(api.patch<EmissionFactor>(`/emission-factors/${enc(id)}`, b)),
  remove: (id: string) => data(api.delete<{ id: string; deleted: boolean }>(`/emission-factors/${enc(id)}`)),
};

export const scope3Api = {
  categories: () => data(api.get<string[]>("/scope3/categories")),
  list: () => data(api.get<Scope3Entry[]>("/scope3")),
  create: (b: Scope3Input) => data(api.post<Scope3Entry>("/scope3", b)),
  update: (id: string, b: Scope3Input) => data(api.put<Scope3Entry>(`/scope3/${enc(id)}`, b)),
  remove: (id: string) => data(api.delete<{ id: string; deleted: boolean }>(`/scope3/${enc(id)}`)),
  review: (id: string, decision: "Approve" | "Reject", comment: string) => data(api.post<Scope3Entry>(`/scope3/${enc(id)}/review`, { decision, comment })),
};

export const initiativesApi = {
  list: () => data(api.get<Initiative[]>("/initiatives")),
  create: (body: InitiativeCreatePayload) => data(api.post<Initiative>("/initiatives", body)),
  update: (id: string, body: InitiativePatch) => data(api.patch<Initiative>(`/initiatives/${enc(id)}`, body)),
  assumptions: () => data(api.get<InitiativeAssumptions>("/initiatives/assumptions")),
  saveAssumptions: (b: InitiativeAssumptions) => data(api.put<InitiativeAssumptions>("/initiatives/assumptions", b)),
  analysis: () => data(api.get<InitiativeAnalysis>("/initiatives/analysis")),
  advance: (id: string, step = 10) => data(api.post<Initiative>(`/initiatives/${enc(id)}/advance`, { step })),
};

export const documentsApi = {
  list: () => data(api.get<DocumentRec[]>("/documents")),
  upload: (v: { file: File; type: string; facilityId: string; month: string; linkedRecord?: string }) => {
    const fd = new FormData();
    fd.append("file", v.file);
    fd.append("type", v.type);
    fd.append("facilityId", v.facilityId);
    fd.append("month", v.month);
    if (v.linkedRecord) fd.append("linkedRecord", v.linkedRecord);
    return data(api.post<DocumentRec>("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 }));
  },
  remove: (id: string) => data(api.delete<{ id: string; deleted: boolean }>(`/documents/${enc(id)}`)),
  download: async (doc: Pick<DocumentRec, "id" | "name">) => {
    const res = await api.get<Blob>(`/documents/${enc(doc.id)}/download`, { responseType: "blob", timeout: 120_000 });
    saveBlob(res.data, doc.name);
  },
};

export const usersApi = {
  list: () => data(api.get<UserRec[]>("/users")),
};

export const auditApi = {
  list: () => data(api.get<AuditEntry[]>("/audit")),
};

export const periodsApi = {
  openNext: (body: { submissionDue?: string; approvalDue?: string } = {}) => data(api.post<ReportingPeriod>("/reporting-periods", body)),
  setStatus: (period: string, status: "In Review" | "Locked") =>
    data(api.post<ReportingPeriod>(`/reporting-periods/${enc(period)}/status`, { status })),
};

export const alertsApi = {
  list: (period?: string) => data(api.get<AiAlert[]>("/alerts", { params: period ? { period } : undefined })),
};

const inventoryParams = (q: InventoryQuery) =>
  Object.fromEntries(Object.entries({ from: q.from, to: q.to, basis: q.basis, facility_id: q.facilityId }).filter(([, v]) => v && v !== "all"));

export const reportsApi = {
  preview: (q: InventoryQuery) => data(api.get<InventoryReport>("/reports/inventory", { params: inventoryParams(q) })),
  download: async (fmt: "xlsx" | "pdf" | "csv", q: InventoryQuery) => {
    const res = await api.get<Blob>(`/reports/inventory.${fmt}`, { params: inventoryParams(q), responseType: "blob", timeout: 120_000 });
    const name = /filename="?([^";]+)"?/.exec(String(res.headers["content-disposition"] ?? ""))?.[1] ?? `ghg-inventory.${fmt}`;
    saveBlob(res.data, name);
  },
};

export const targetsApi = {
  get: () => data(api.get<TargetsView>("/targets")),
  setBaseline: (b: { start: string; end: string }) => data(api.put<TargetsView>("/targets/baseline", b)),
  setTargets: (targets: EmissionTarget[]) => data(api.put<TargetsView>("/targets", { targets })),
};

export const validationRulesApi = {
  get: () => data(api.get<ValidationRules>("/validation-rules")),
  save: (b: ValidationRules) => data(api.put<ValidationRules>("/validation-rules", b)),
};

export const referenceApi = {
  get: <T>(key: string) => data(api.get<T[]>(`/reference/${enc(key)}`)),
};

export const adminToolsApi = {
  status: () => data(api.get<{ connected: boolean; facilityCount: number }>("/admin/db/status")),
  crudTest: () => data(api.post<Record<string, unknown>>("/admin/db/crud-test")),
  seedFacilities: () => data(api.post<unknown[]>("/admin/db/seed-facilities")),
};
