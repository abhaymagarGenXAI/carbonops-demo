/**
 * TanStack Query hooks — the only place components get server data from.
 * Replaces the TanStack Start route loaders / server functions / in-memory store.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/services/api";
import {
  alertsApi,
  assetsApi,
  auditApi,
  documentsApi,
  emissionFactorsApi,
  scope3Api,
  emissionsRecalc,
  emissionsApi,
  energyApi,
  type EnergyEdit,
  facilitiesApi,
  periodsApi,
  initiativesApi,
  referenceApi,
  submissionsApi,
  usersApi,
  type AssetChanges,
  type FacilityChanges,
  type FacilityInput,
  validationRulesApi,
  targetsApi,
  reportsApi,
} from "@/services/entities";
import type {
  Asset,
  InitiativeCreatePayload,
  RecentActivityItem,
  ReportingPeriod,
  ReviewDecision,
  SubmissionSavePayload,
  EmissionTarget,
  InventoryQuery,
  InitiativeAssumptions,
  InitiativePatch,
  EmissionFactorInput,
  Scope3Input,
  ValidationRules,
  Workflow,
} from "@/types/domain";

/** Data other users change (submissions, reviews, evidence, alerts) is re-read every 15 s while the tab is visible,
 *  so one person's action shows up for everyone else without a manual browser refresh. */
const LIVE = { refetchInterval: 15_000, staleTime: 10_000 } as const;

export const qk = {
  facilities: ["facilities"] as const,
  assets: ["assets"] as const,
  submissions: ["submissions"] as const,
  energy: ["energy-records"] as const,
  emissions: ["emission-records"] as const,
  factors: ["emission-factors"] as const,
  scope3: ["scope3"] as const,
  initiatives: ["initiatives"] as const,
  documents: ["documents"] as const,
  users: ["users"] as const,
  audit: ["audit"] as const,
  alerts: ["alerts"] as const,
  rules: ["validation-rules"] as const,
  targets: ["targets"] as const,
  reference: (key: string) => ["reference", key] as const,
};

/* ------------------------------------------------------------------ reads */
export const useFacilities = () => useQuery({ queryKey: qk.facilities, queryFn: facilitiesApi.list });
export const useAssets = () => useQuery({ queryKey: qk.assets, queryFn: assetsApi.list });
export const useSubmissions = () => useQuery({ queryKey: qk.submissions, queryFn: submissionsApi.list, ...LIVE });
export const useEnergyRecords = () => useQuery({ queryKey: qk.energy, queryFn: energyApi.list, ...LIVE });
export const useEmissions = () => useQuery({ queryKey: qk.emissions, queryFn: emissionsApi.list, ...LIVE });
export const useEmissionFactors = () => useQuery({ queryKey: qk.factors, queryFn: emissionFactorsApi.list });
export const useInitiatives = () => useQuery({ queryKey: qk.initiatives, queryFn: initiativesApi.list });
export const useDocuments = () => useQuery({ queryKey: qk.documents, queryFn: documentsApi.list, ...LIVE });
export const useAuditTrail = () => useQuery({ queryKey: qk.audit, queryFn: auditApi.list, ...LIVE });
export const useUsers = (enabled: boolean) => useQuery({ queryKey: qk.users, queryFn: usersApi.list, enabled });

const useReference = <T,>(key: string) =>
  useQuery({ queryKey: qk.reference(key), queryFn: () => referenceApi.get<T>(key), staleTime: 5 * 60_000 });
export const useReportingPeriods = () => useReference<ReportingPeriod>("reportingPeriods");
export const useWorkflows = () => useReference<Workflow>("workflows");
export const useInventoryPreview = (q: InventoryQuery, enabled: boolean) =>
  useQuery({ queryKey: ["reports", "inventory", q], queryFn: () => reportsApi.preview(q), enabled });
export const useScope3 = () => useQuery({ queryKey: qk.scope3, queryFn: scope3Api.list, ...LIVE });
export const useScope3Categories = () => useQuery({ queryKey: ["scope3", "categories"], queryFn: scope3Api.categories, staleTime: Infinity });
export const useTargets = () => useQuery({ queryKey: qk.targets, queryFn: targetsApi.get, ...LIVE });
export const useSaveBaseline = () => useApiMutation((b: { start: string; end: string }) => targetsApi.setBaseline(b), [qk.targets, qk.initiatives]);
export const useSaveTargets = () => useApiMutation((t: EmissionTarget[]) => targetsApi.setTargets(t), [qk.targets, qk.initiatives]);
export const useValidationRules = () => useQuery({ queryKey: qk.rules, queryFn: validationRulesApi.get });
export const useSaveValidationRules = () => useApiMutation((b: ValidationRules) => validationRulesApi.save(b), [qk.rules, qk.submissions]);
/** Alerts for one reporting period (period-specific checks follow it; rejections/rework are always listed). */
export const useAlerts = (period?: string) => useQuery({ queryKey: [...qk.alerts, period ?? "default"], queryFn: () => alertsApi.list(period), enabled: !!period, ...LIVE });
export const useAiAlerts = () => useQuery({ queryKey: qk.alerts, queryFn: () => alertsApi.list(), ...LIVE });
export const useRecentActivity = () => useReference<RecentActivityItem>("recentActivity");

/* -------------------------------------------------------------- mutations */
type Keys = readonly (readonly unknown[])[];

/** Runs `fn`, then refetches the affected queries *before* resolving, so
 *  `await mutateAsync()` behaves like the old `await router.invalidate()`. */
function useApiMutation<TVars, TData>(fn: (vars: TVars) => Promise<TData>, invalidate: Keys) {
  const qc = useQueryClient();
  return useMutation<TData, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all([...invalidate, qk.audit, qk.alerts].map((queryKey) => qc.invalidateQueries({ queryKey })));
    },
  });
}

export const useCreateFacility = () => useApiMutation((b: FacilityInput) => facilitiesApi.create(b), [qk.facilities]);
export const useUpdateFacility = () =>
  useApiMutation((v: { id: string; changes: FacilityChanges }) => facilitiesApi.update(v.id, v.changes), [qk.facilities]);
export const useDeleteFacility = () => useApiMutation((id: string) => facilitiesApi.remove(id), [qk.facilities]);

export const useCreateAsset = () => useApiMutation((b: Asset) => assetsApi.create(b), [qk.assets]);
export const useUpdateAsset = () =>
  useApiMutation((v: { id: string; changes: AssetChanges }) => assetsApi.update(v.id, v.changes), [qk.assets]);
export const useDeleteAsset = () => useApiMutation((id: string) => assetsApi.remove(id), [qk.assets]);

export const useSaveSubmission = () =>
  useApiMutation((b: SubmissionSavePayload) => submissionsApi.save(b), [qk.submissions, qk.emissions, qk.energy, qk.targets]);
export const useReviewSubmission = () =>
  useApiMutation(
    (v: { id: string; status: ReviewDecision; comment: string; revision?: number | undefined }) => submissionsApi.review(v.id, v.status, v.comment, v.revision),
    [qk.submissions, qk.emissions, qk.energy, qk.targets],
  );
export const useRecalculateEmissions = () =>
  useApiMutation((v: { month?: string | undefined; facilityId?: string | undefined; dryRun: boolean }) => emissionsRecalc(v), [qk.emissions]);
export const useReviewEmission = () =>
  useApiMutation(
    (v: { id: string; status: ReviewDecision; comment: string }) => emissionsApi.review(v.id, v.status, v.comment),
    [qk.emissions, qk.submissions, qk.energy],
  );

export const useUpdateEnergyRecord = () =>
  useApiMutation((v: { id: string; changes: EnergyEdit }) => energyApi.update(v.id, v.changes), [qk.energy]);
export const useReconcileEnergy = () =>
  useApiMutation((v: { month?: string | undefined; facilityId?: string | undefined; dryRun: boolean }) => energyApi.reconcile(v), [qk.energy]);

const PERIODS = qk.reference("reportingPeriods");
export const useOpenNextPeriod = () => useApiMutation(() => periodsApi.openNext(), [PERIODS, qk.submissions]);
export const useSetPeriodStatus = () =>
  useApiMutation((v: { period: string; status: "In Review" | "Locked" }) => periodsApi.setStatus(v.period, v.status), [PERIODS]);

export const useDeleteDocument = () => useApiMutation((id: string) => documentsApi.remove(id), [qk.documents]);
export const useUploadDocument = () => useApiMutation((v: Parameters<typeof documentsApi.upload>[0]) => documentsApi.upload(v), [qk.documents]);
export const useImportCommit = () =>
  useApiMutation((v: Parameters<typeof submissionsApi.importCommit>[0]) => submissionsApi.importCommit(v), [qk.submissions, qk.emissions, qk.energy, qk.targets]);

export const useCreateInitiative = () =>
  useApiMutation((b: InitiativeCreatePayload) => initiativesApi.create(b), [qk.initiatives]);
export const useInitiativeAnalysis = () => useQuery({ queryKey: [...qk.initiatives, "analysis"], queryFn: initiativesApi.analysis, ...LIVE });
export const useUpdateInitiative = () =>
  useApiMutation((v: { id: string; patch: InitiativePatch }) => initiativesApi.update(v.id, v.patch), [qk.initiatives]);
export const useSaveAssumptions = () => useApiMutation((b: InitiativeAssumptions) => initiativesApi.saveAssumptions(b), [qk.initiatives]);
const S3 = [qk.scope3, ["reports"]] as const;
export const useCreateScope3 = () => useApiMutation((b: Scope3Input) => scope3Api.create(b), S3);
export const useUpdateScope3 = () => useApiMutation((v: { id: string; body: Scope3Input }) => scope3Api.update(v.id, v.body), S3);
export const useDeleteScope3 = () => useApiMutation((id: string) => scope3Api.remove(id), S3);
export const useReviewScope3 = () =>
  useApiMutation((v: { id: string; decision: "Approve" | "Reject"; comment: string }) => scope3Api.review(v.id, v.decision, v.comment), S3);
export const useCreateFactor = () => useApiMutation((b: EmissionFactorInput) => emissionFactorsApi.create(b), [qk.factors]);
export const useUpdateFactor = () =>
  useApiMutation((v: { id: string; body: Partial<EmissionFactorInput> }) => emissionFactorsApi.update(v.id, v.body), [qk.factors]);
export const useDeleteFactor = () => useApiMutation((id: string) => emissionFactorsApi.remove(id), [qk.factors]);
export const useAdvanceInitiative = () => useApiMutation((id: string) => initiativesApi.advance(id), [qk.initiatives]);
