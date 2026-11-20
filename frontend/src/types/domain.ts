// Domain types shared by the UI and the API client (mirror backend/app/schemas).

export type Status = "Draft" | "Submitted" | "Under Review" | "Approved" | "Rejected";

export interface Facility {
  id: string;
  name: string;
  code: string;
  region: string;
  type: string;
  manager: string;
  units: string[];
  commissioned: string;
  employees: number;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface Asset {
  id: string;
  name: string;
  facilityId: string;
  unit: string;
  type: string;
  status: "Operational" | "Under Maintenance" | "Shutdown" | "Standby";
  energySource: string;
  operatingHours: number;
  engineer: string;
  lastInspection: string;
  carbonCategory: string;
  emissionSourceType: string;
  capacity: string;
}

export interface Submission {
  id: string;
  facilityId: string;
  unit: string;
  month: string;
  status: Status;
  submittedBy: string;
  updatedAt: string;
  reviewer: string;
  reviewerComments: string;
  validation: "Passed" | "Warnings" | "Not Run";
  completeness: number;
  anomalies: string[];
  revision: number;
  data: ActivityData;
  reviewAction?: "None" | "Clarification Required";
  submittedAt?: string | null;
  reviewedAt?: string | null;
}

export interface ActivityData {
  productionVolume: number;
  electricity: number;
  diesel: number;
  naturalGas: number;
  steam: number;
  water: number;
  flareGas: number;
  methaneLeak: number;
  renewable: number;
  operatingHours: number;
  remarks: string;
  notes: string;
}

export interface EnergyRecord {
  id: string;
  facilityId: string;
  month: string;
  stream: "Electricity" | "Diesel" | "Natural Gas" | "Steam" | "Renewable Energy";
  quantity: number;
  unit: string;
  meterRef: string;
  invoiceRef: string;
  cost: number;
  validation: "Validated" | "Pending" | "Anomaly" | "Missing";
  /** status of the source submission (null for legacy unlinked records) */
  submissionStatus?: string | null;
  variance: number;
  /** energy content (GJ); null for steam / renewable generation */
  energyGj?: number | null;
  /** submission the quantity is derived from (null on legacy, unreconciled records) */
  submissionId?: string | null;
}

export interface EnergyReconcileResult {
  dryRun: boolean;
  evaluated: number;
  created: number;
  updated: number;
  unchanged: number;
  skipped: { target: string; reason: string }[];
  items: {
    id: string; facilityId: string; month: string; stream: string; action: string;
    oldQuantity: number | null; newQuantity: number; oldValidation: string | null; newValidation: string;
    oldVariance: number | null; newVariance: number; excluded: boolean;
  }[];
}

export interface EmissionRecord {
  id: string;
  facilityId: string;
  month: string;
  source: string;
  activityValue: number;
  unit: string;
  factor: number;
  factorUnit: string;
  factorRef: string;
  scope: "Scope 1" | "Scope 2" | "Scope 3";
  co2e: number;
  prevCo2e: number;
  calcStatus: "Calculated" | "Recalculation Required" | "Pending";
  reviewStatus: Status;
  comments: { by: string; at: string; text: string }[];
  /** calculation trace; absent on legacy records until a recalculation links them */
  factorId?: string | null;
  submissionId?: string | null;
  formula?: string | null;
  calcNote?: string | null;
  calculatedAt?: string | null;
}

export interface RecalculateItem {
  id: string;
  facilityId: string;
  month: string;
  source: string;
  action: "create" | "update";
  oldCo2e: number | null;
  newCo2e: number;
  oldFactor: number | null;
  newFactor: number;
  factorId: string;
  reason: string;
}

export interface RecalculateResult {
  dryRun: boolean;
  evaluated: number;
  created: number;
  updated: number;
  traceLinked: number;
  unchanged: number;
  skipped: { target: string; reason: string }[];
  items: RecalculateItem[];
}

export interface Initiative {
  id: string;
  name: string;
  type: string;
  owner: string;
  facilityId: string;
  status: "Planned" | "In Progress" | "On Hold" | "Completed";
  expectedReduction: number;
  actualReduction: number;
  investment: number;
  annualSavings?: number;
  roi: number;
  annualCost?: number | null;
  maccCost?: number | null;
  paybackYears?: number | null;
  completion: number;
  startDate: string;
  endDate: string;
  timeline: "On Track" | "At Risk" | "Delayed" | "Complete";
  priority: "Critical" | "High" | "Medium" | "Low";
  dependencies: string;
  notes: string;
  milestones: { name: string; date: string; done: boolean }[];
}

export interface DocumentRec {
  id: string;
  name: string;
  type: string;
  facilityId: string;
  month: string;
  size: string;
  format: "PDF" | "XLSX" | "CSV" | "DOCX";
  uploadedBy: string;
  uploadedAt: string;
  linkedRecord: string;
  version: string;
  versions: { version: string; at: string; by: string; note: string }[];
  /** real stored file; false for legacy metadata-only records */
  hasFile?: boolean;
  sizeBytes?: number | null;
  sha256?: string | null;
}

export interface ImportRow {
  row: number;
  facilityId: string | null;
  facilityName: string | null;
  unit: string | null;
  month: string | null;
  data: Record<string, number | string> | null;
  errors: string[];
  warnings: string[];
  existingStatus: string | null;
  importable: boolean;
}

export interface ImportPreview {
  fileName: string;
  sheet: string | null;
  rowCount: number;
  importableRows: number;
  errorRows: number;
  unmappedColumns: string[];
  rows: ImportRow[];
}

export interface ImportCommitResult {
  saved: number;
  failed: number;
  results: { facilityId: string; month: string; ok: boolean; submissionId: string | null; detail: string }[];
}

export interface UserRec {
  id: string;
  name: string;
  email: string;
  role: string;
  appRole: AppRole;
  facility: string;
  status: "Active" | "Suspended";
  lastLogin: string;
}

export interface EmissionFactor {
  id: string;
  source: string;
  scope: "Scope 1" | "Scope 2" | "Scope 3";
  value: number;
  unit: string;
  reference: string;
  validFrom: string;
  status: "Active" | "Superseded";
  category?: string | null;
}

export type EmissionFactorInput = Omit<EmissionFactor, "id"> & { id?: string };

export interface Scope3Entry {
  id: string; month: string; category: string; source: string; facilityId: string | null; description: string;
  activityValue: number; unit: string; method: string; factor: number; factorUnit: string; factorRef: string; factorId: string;
  co2e: number; formula: string; calcNote: string; status: "Submitted" | "Approved" | "Rejected";
  createdBy: string; createdById: string; reviewer: string | null; reviewComment: string | null; reviewedAt: string | null;
}
export interface Scope3Input { month: string; category: string; source: string; activityValue: number; facilityId: string | null; description: string }


export type AppRole = "Plant Engineer" | "Sustainability Manager" | "Administrator";

export interface AuditEntry {
  id: string;
  at: string;
  who: string;
  action: string;
  target: string;
  detail: string;
}

export interface ReportingPeriod {
  id: string;
  period: string;
  status: string;
  submissionDue: string;
  approvalDue: string;
  lockedOn: string;
}

export interface Workflow {
  id: string;
  name: string;
  steps: string;
  sla: string;
  escalation: string;
  status: string;
}

export interface AiAlert {
  id: string;
  /** anomaly | approval | due | rejected | rework | inspection */
  kind?: string;
  submissionId?: string | null;
  severity: string;
  title: string;
  detail: string;
  action: string;
}

export interface RecentActivityItem {
  at: string;
  who: string;
  what: string;
  type: string;
}

/** Payload for saving a draft / submitting activity data (server computes id, validation, completeness). */
export interface SubmissionSavePayload {
  facilityId: string;
  unit: string;
  month: string;
  status: "Draft" | "Submitted";
  data: ActivityData;
  /** Revision the form was opened on; the API refuses the save if someone else changed the submission since. */
  revision?: number;
}

export type ReviewDecision = "Approved" | "Rejected" | "Under Review";

export interface InitiativeCreatePayload {
  name: string;
  type: string;
  owner: string;
  facilityId: string;
  expectedReduction: number;
  investment: number;
  startDate: string;
  endDate: string;
  priority: Initiative["priority"];
  notes: string;
  annualSavings?: number;
}

export interface ValidationLimit { field: string; max: number; enabled: boolean; block: boolean }
export interface ValidationRules {
  spikeEnabled: boolean; spikePct: number; highPct: number; historyMonths: number; spikeBlockHigh: boolean;
  zeroEnabled: boolean; zeroBlock: boolean; limits: ValidationLimit[]; inspectionIntervalDays: number;
}

export interface BaselineSnapshot {
  start: string; end: string; months: number; facilities: number; recordCount: number;
  scope1: number; scope2: number; total: number; annualScope1: number; annualScope2: number; annualTotal: number;
  basis: string; setAt: string; setBy: string; byFacility?: Record<string, number>;
}
export type TargetScope = "Total" | "Scope 1" | "Scope 2";
export interface EmissionTarget { scope: TargetScope; reductionPct: number; targetYear: number }
export interface TargetProgress extends EmissionTarget {
  baselineAnnual: number; targetAnnual: number; monthsEvaluated: number; latestMonth: string | null;
  cumulativeActual: number; cumulativeAllowed: number; currentActual: number | null; currentAllowed: number | null;
  achievedReductionPct: number | null; requiredReductionPct: number | null;
  status: "On track" | "At risk" | "Off track" | "No data yet";
}
export interface TargetSeriesRow {
  month: string; phase: "baseline" | "tracking";
  actual: Record<TargetScope, number>; allowed: Partial<Record<TargetScope, number>>;
}
export interface TargetsView {
  baseline: BaselineSnapshot | null; targets: EmissionTarget[]; progress: TargetProgress[]; series: TargetSeriesRow[];
  completeThrough: string | null; incompleteMonths: string[]; atRiskTolerancePct: number;
}

export interface InitiativeAssumptions { carbonValuePerTonne: number; discountRatePct: number; lifetimeYears: number }
export interface InitiativeAnalysis {
  assumptions: InitiativeAssumptions;
  portfolio: { count: number; expected: number; verified: number; investment: number };
  macc: { id: string; name: string; facilityId: string; status: string; expectedReduction: number; maccCost: number; cumulativeReduction: number }[];
  targetCoverage: { targetYear: number; reductionPct: number; gapAnnual: number; delivered: number; pipeline: number; onHold: number; coveragePct: number | null; uncovered: number } | null;
  facilityMeasured: { facilityId: string; initiativeIds: string[]; plannedAnnual: number; verifiedAnnual: number; baselineMonthly: number; actualMonthly: number | null; measuredAnnualReduction: number | null; monthsEvaluated: number }[];
  baselineSet: boolean;
}
export type InitiativePatch = Partial<Pick<Initiative, "actualReduction" | "annualSavings" | "milestones" | "status" | "notes">>;

export interface InventoryQuery { from?: string; to?: string; basis: "approved" | "pending"; facilityId?: string }
export interface InventoryReport {
  scope: { from: string | null; to: string | null; basis: string; facility: string };
  summary: {
    totals: { scope1: number; scope2: number; scope3: number; total: number };
    bySource: { source: string; scope: string; unit: string; activity: number; co2e: number; sharePct: number }[];
    byFacility: { facilityId: string; facility: string; scope1: number; scope2: number; scope3: number; total: number }[];
    byMonth: { month: string; scope1: number; scope2: number; scope3: number; total: number }[];
    coverage: { recordCount: number; tracedRecords: number; legacyUntraced: number; incompleteMonths: string[] };
  };
  warnings: string[];
}
