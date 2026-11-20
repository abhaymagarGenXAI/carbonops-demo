/**
 * Compatibility facade.
 *
 * Pages used to read everything from an in-memory `useStore()`. To keep the existing component
 * structure, `useStore()` keeps its shape but is now backed by TanStack Query talking to
 * FastAPI (see hooks/useApi.ts). Mutations return promises so callers can await + toast errors.
 */
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import {
  useAiAlerts,
  useAssets,
  useAuditTrail,
  useDocuments,
  useEmissionFactors,
  useEmissions,
  useEnergyRecords,
  useFacilities,
  useInitiatives,
  useReportingPeriods,
  useReviewEmission,
  useReviewSubmission,
  useSaveSubmission,
  useCreateInitiative,
  useAdvanceInitiative,
  useSubmissions,
  useUsers,
  useWorkflows,
} from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import type {
  AiAlert,
  AppRole,
  Asset,
  AuditEntry,
  DocumentRec,
  EmissionFactor,
  EmissionRecord,
  EnergyRecord,
  Facility,
  Initiative,
  InitiativeCreatePayload,
  RecentActivityItem,
  ReportingPeriod,
  ReviewDecision,
  Submission,
  SubmissionSavePayload,
  UserRec,
  Workflow,
} from "@/types/domain";

interface StoreValue {
  facilities: Facility[];
  facilityName: (id: string) => string;
  assets: Asset[];
  submissions: Submission[];
  energyRecords: EnergyRecord[];
  emissions: EmissionRecord[];
  initiatives: Initiative[];
  documents: DocumentRec[];
  users: UserRec[];
  factors: EmissionFactor[];
  audit: AuditEntry[];
  reportingPeriods: ReportingPeriod[];
  workflows: Workflow[];
  aiAlerts: AiAlert[];
  recentActivity: RecentActivityItem[];
  /** ["2026-01", …] derived from reporting periods */
  months: string[];
  /** the reporting period whose status is "Open" */
  currentPeriod: string;

  role: AppRole;
  setRole: (r: AppRole) => void;

  isLoading: boolean;
  error: Error | null;
  reload: () => void;

  saveSubmission: (payload: SubmissionSavePayload) => Promise<Submission>;
  setSubmissionStatus: (id: string, status: ReviewDecision, comment?: string, revision?: number) => Promise<Submission>;
  setEmissionReview: (id: string, status: ReviewDecision, comment?: string) => Promise<EmissionRecord>;
  createInitiative: (payload: InitiativeCreatePayload) => Promise<Initiative>;
  advanceInitiative: (id: string) => Promise<Initiative>;
}

const StoreContext = createContext<StoreValue | null>(null);
const EMPTY: never[] = [];

export function StoreProvider({ children }: { children: ReactNode }) {
  const { role, setRole, user } = useAuth();

  const facilities = useFacilities();
  const assets = useAssets();
  const submissions = useSubmissions();
  const energy = useEnergyRecords();
  const emissions = useEmissions();
  const initiatives = useInitiatives();
  const documents = useDocuments();
  const factors = useEmissionFactors();
  const audit = useAuditTrail();
  const periods = useReportingPeriods();
  const workflows = useWorkflows();
  const alerts = useAiAlerts();
  const users = useUsers(user?.appRole === "Administrator");

  const queries = [facilities, assets, submissions, energy, emissions, initiatives, documents, factors, audit, periods, workflows, alerts];

  const saveSub = useSaveSubmission();
  const reviewSub = useReviewSubmission();
  const reviewEm = useReviewEmission();
  const createInit = useCreateInitiative();
  const advanceInit = useAdvanceInitiative();

  const facilityList = facilities.data ?? EMPTY;
  const periodList = periods.data ?? EMPTY;

  const facilityName = useCallback(
    (id: string) => facilityList.find((f) => f.id === id)?.name ?? id,
    [facilityList],
  );

  const isLoading = queries.some((q) => q.isLoading);
  const error = (queries.find((q) => q.isError)?.error as Error | undefined) ?? null;

  const { mutateAsync: saveSubmissionAsync } = saveSub;
  const { mutateAsync: reviewSubAsync } = reviewSub;
  const { mutateAsync: reviewEmAsync } = reviewEm;
  const { mutateAsync: createInitAsync } = createInit;
  const { mutateAsync: advanceInitAsync } = advanceInit;

  const value = useMemo<StoreValue>(() => {
    const months = periodList.map((p) => p.period);
    return {
      facilities: facilityList,
      facilityName,
      assets: assets.data ?? EMPTY,
      submissions: submissions.data ?? EMPTY,
      energyRecords: energy.data ?? EMPTY,
      emissions: emissions.data ?? EMPTY,
      initiatives: initiatives.data ?? EMPTY,
      documents: documents.data ?? EMPTY,
      users: users.data ?? EMPTY,
      factors: factors.data ?? EMPTY,
      audit: audit.data ?? EMPTY,
      reportingPeriods: periodList,
      workflows: workflows.data ?? EMPTY,
      aiAlerts: alerts.data ?? EMPTY,
      // Live: the latest audit entries (every save, review, upload, recalculation and period change writes one).
      recentActivity: (audit.data ?? EMPTY).slice(0, 8).map((a) => ({ at: a.at, who: a.who, what: `${a.action} · ${a.target} — ${a.detail}`, type: a.action })),
      months,
      currentPeriod: periodList.find((p) => p.status === "Open")?.period ?? months[months.length - 1] ?? "",
      role,
      setRole,
      isLoading,
      error,
      reload: () => queries.forEach((q) => void q.refetch()),
      saveSubmission: (p) => saveSubmissionAsync(p),
      setSubmissionStatus: (id, status, comment = "", revision) => reviewSubAsync({ id, status, comment, revision }),
      setEmissionReview: (id, status, comment = "") => reviewEmAsync({ id, status, comment }),
      createInitiative: (p) => createInitAsync(p),
      advanceInitiative: (id) => advanceInitAsync(id),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    facilityList, facilityName, assets.data, submissions.data, energy.data, emissions.data, initiatives.data,
    documents.data, users.data, factors.data, audit.data, periodList, workflows.data, alerts.data,
    role, setRole, isLoading, error,
    saveSubmissionAsync, reviewSubAsync, reviewEmAsync, createInitAsync, advanceInitAsync,
  ]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside StoreProvider");
  return ctx;
}
