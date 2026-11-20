import { useMemo, useState } from "react";
import {
  Building2,
  Eye,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import {
  DataTable,
  type Column,
} from "@/components/data-table";

import {
  Field,
  PageHeader,
  SectionCard,
  StatCard,
} from "@/components/page-parts";

import { StatusBadge } from "@/components/status-badge";

import { useStore } from "@/lib/store";
import { type Asset } from "@/types/domain";
import {
  useCreateAsset,
  useCreateFacility,
  useDeleteAsset,
  useDeleteFacility,
  useUpdateAsset,
  useUpdateFacility,
} from "@/hooks/useApi";
import { usePageMeta } from "@/hooks/use-page-meta";

type DbFacility = {
  facilityId: string;
  name: string;
  code: string;
  region: string;
  type: string;
  manager: string;
  units: string[];
  commissioned: string;
  employees: number;
  createdAt: string | null;
  updatedAt: string | null;
};

type FacilityForm = {
  facilityId: string;
  name: string;
  code: string;
  region: string;
  type: string;
  manager: string;
  units: string;
  commissioned: string;
  employees: number;
};

const emptyFacilityForm: FacilityForm = {
  facilityId: "",
  name: "",
  code: "",
  region: "",
  type: "Production Facility",
  manager: "",
  units: "",
  commissioned: "",
  employees: 0,
};

const assetTypes = [
  "Boiler",
  "Gas Compressor",
  "Gas Turbine",
  "Diesel Generator",
  "Crude Storage Tank",
  "Trunk Pipeline",
  "Flare Stack",
  "Process Heater",
  "Grid Intake Substation",
  "Solar Array",
];

type FieldErrors = {
  name?: string;
  capacity?: string;
  operatingHours?: string;
};

const emptyAsset = (facilities: DbFacility[]): Asset => {
  const firstFacility = facilities[0];

  return {
    id: "",
    name: "",
    facilityId: firstFacility?.facilityId ?? "",
    unit: firstFacility?.units?.[0] ?? "",
    type: "Boiler",
    status: "Operational",
    energySource: "Natural Gas",
    operatingHours: 720,
    engineer: "K. Iyer",
    lastInspection: "2026-07-01",
    carbonCategory: "Scope 1",
    emissionSourceType: "Stationary Combustion",
    capacity: "",
  };
};

export default function AssetsPage() {
  usePageMeta(
    "Facilities & Assets — CarbonOps AI",
    "Manage the Oil & Gas facility hierarchy, production units and emission-source asset inventory with engineer ownership and inspection status.",
  );

  /*
   * Facilities and assets come from FastAPI/MongoDB through TanStack Query (see lib/store.tsx).
   * Mutations below invalidate + refetch those queries, replacing `router.invalidate()`.
   */
  const { facilities: apiFacilities, assets, role, submissions } = useStore();

  const createFacility = useCreateFacility();
  const updateFacility = useUpdateFacility();
  const deleteFacility = useDeleteFacility();
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset();
  const deleteAsset = useDeleteAsset();

  // This page's local DbFacility type keys facilities by `facilityId`; the API exposes `id`.
  const facilities: DbFacility[] = useMemo(
    () =>
      apiFacilities.map((f) => ({
        facilityId: f.id,
        name: f.name,
        code: f.code,
        region: f.region,
        type: f.type,
        manager: f.manager,
        units: f.units,
        commissioned: f.commissioned,
        employees: f.employees,
        createdAt: f.createdAt ?? null,
        updatedAt: f.updatedAt ?? null,
      })),
    [apiFacilities],
  );

  const openCreateFacility = () => {
  setFacilityBeingEdited(null);

  setFacilityForm({
    ...emptyFacilityForm,
  });

  setFacilityErrors({});
  setFacilityDialogOpen(true);
};

const openEditFacility = (facility: DbFacility) => {
  setFacilityBeingEdited(facility);

  setFacilityForm({
    facilityId: facility.facilityId,
    name: facility.name,
    code: facility.code,
    region: facility.region,
    type: facility.type,
    manager: facility.manager,
    units: facility.units.join(", "),
    commissioned: facility.commissioned,
    employees: facility.employees,
  });

  setFacilityErrors({});
  setFacilityDialogOpen(true);
};

const saveFacility = async () => {
  const errors: typeof facilityErrors = {};

  if (!facilityForm.name.trim()) {
    errors.name = "Facility name is required.";
  }

  if (!facilityForm.code.trim()) {
    errors.code = "Facility code is required.";
  }

  if (!facilityForm.region.trim()) {
    errors.region = "Region is required.";
  }

  if (!facilityForm.manager.trim()) {
    errors.manager = "Facility manager is required.";
  }

  if (!facilityForm.commissioned) {
    errors.commissioned =
      "Commissioned date is required.";
  }

  setFacilityErrors(errors);

  if (Object.keys(errors).length > 0) {
    return;
  }

  setFacilitySaving(true);

  try {
    const units = facilityForm.units
      .split(",")
      .map((unit) => unit.trim())
      .filter(Boolean);

    if (facilityBeingEdited) {
      await updateFacility.mutateAsync({
        id: facilityBeingEdited.facilityId,
        changes: {
            name: facilityForm.name.trim(),
            code: facilityForm.code.trim(),
            region: facilityForm.region.trim(),
            type: facilityForm.type.trim(),
            manager: facilityForm.manager.trim(),
            units,
            commissioned:
              facilityForm.commissioned,
            employees: Math.max(
              0,
              facilityForm.employees,
            ),
          },
      });

      toast.success("Facility updated", {
        description: `${facilityForm.name} has been updated.`,
      });
    } else {
      const facilityId =
        facilityForm.facilityId.trim() ||
        `${facilityForm.code
          .trim()
          .toUpperCase()
          .replace(/\s+/g, "-")}-${Date.now()}`;

      await createFacility.mutateAsync({
          id: facilityId,
          name: facilityForm.name.trim(),
          code: facilityForm.code.trim(),
          region: facilityForm.region.trim(),
          type: facilityForm.type.trim(),
          manager: facilityForm.manager.trim(),
          units,
          commissioned:
            facilityForm.commissioned,
          employees: Math.max(
            0,
            facilityForm.employees,
          ),
        });

      toast.success("Facility created", {
        description: `${facilityForm.name} has been added to MongoDB.`,
      });
    }

    setFacilityDialogOpen(false);
    setFacilityBeingEdited(null);

    // the mutation already refetched the affected queries
  } catch (error) {
    console.error(
      "Facility save failed:",
      error,
    );

    toast.error(
      facilityBeingEdited
        ? "Failed to update facility"
        : "Failed to create facility",
      {
        description:
          error instanceof Error
            ? error.message
            : "An unexpected error occurred.",
      },
    );
  } finally {
    setFacilitySaving(false);
  }
};

const confirmDeleteFacility = async () => {
  if (!facilityToDelete) return;

  setFacilityDeleting(true);

  try {
    await deleteFacility.mutateAsync(facilityToDelete.facilityId);

    toast.success("Facility deleted", {
      description: `${facilityToDelete.name} has been removed.`,
    });

    setFacilityToDelete(null);

    // the mutation already refetched the affected queries
  } catch (error) {
    console.error(
      "Facility delete failed:",
      error,
    );

    toast.error("Failed to delete facility", {
      description:
        error instanceof Error
          ? error.message
          : "An unexpected error occurred.",
    });
  } finally {
    setFacilityDeleting(false);
  }
};


  const [facilityFilter, setFacilityFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [editing, setEditing] = useState<Asset | null>(null);
  const [detail, setDetail] = useState<Asset | null>(null);
  const [deleting, setDeleting] = useState<Asset | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [assetSaving, setAssetSaving] =
  useState(false);

const [assetDeleting, setAssetDeleting] =
  useState(false);

const canCreateAsset =
  role === "Administrator";

const canEditAsset =
  role === "Administrator" ||
  role === "Plant Engineer";

const canDeleteAsset =
  role === "Administrator";

  const [facilityDialogOpen, setFacilityDialogOpen] =
  useState(false);

const [facilityForm, setFacilityForm] =
  useState<FacilityForm>(emptyFacilityForm);

const [facilityBeingEdited, setFacilityBeingEdited] =
  useState<DbFacility | null>(null);

const [facilityToDelete, setFacilityToDelete] =
  useState<DbFacility | null>(null);

const [facilitySaving, setFacilitySaving] =
  useState(false);

const [facilityDeleting, setFacilityDeleting] =
  useState(false);

const [facilityErrors, setFacilityErrors] = useState<{
  name?: string;
  code?: string;
  region?: string;
  manager?: string;
  commissioned?: string;
}>({});


  const facilityName = (id: string) =>
    facilities.find((facility) => facility.facilityId === id)?.name ?? id;

  const rows = useMemo(
    () =>
      assets.filter(
        (a) =>
          (facilityFilter === "all" ||
            a.facilityId === facilityFilter) &&
          (statusFilter === "all" ||
            a.status === statusFilter),
      ),
    [assets, facilityFilter, statusFilter],
  );

  const columns: Column<Asset>[] = [
    {
      key: "id",
      header: "Asset ID",
      sortable: true,
      value: (a) => a.id,
      render: (a) => (
        <span className="font-medium tabular">
          {a.id}
        </span>
      ),
    },

    {
      key: "name",
      header: "Asset name",
      sortable: true,
      value: (a) => a.name,
    },

    {
      key: "facility",
      header: "Facility",
      sortable: true,
      value: (a) => facilityName(a.facilityId),
      render: (a) => (
        <div>
          <p>{facilityName(a.facilityId)}</p>
          <p className="text-xs text-muted-foreground">
            {a.unit}
          </p>
        </div>
      ),
    },

    {
      key: "type",
      header: "Type",
      sortable: true,
      value: (a) => a.type,
    },

    {
      key: "status",
      header: "Status",
      sortable: true,
      value: (a) => a.status,
      render: (a) => (
        <StatusBadge value={a.status} />
      ),
    },

    {
      key: "energy",
      header: "Energy source",
      value: (a) => a.energySource,
    },

    {
      key: "hours",
      header: "Op. hours",
      align: "right",
      sortable: true,
      value: (a) => a.operatingHours,
    },

    {
      key: "engineer",
      header: "Assigned engineer",
      sortable: true,
      value: (a) => a.engineer,
    },

    {
      key: "inspection",
      header: "Last inspection",
      sortable: true,
      value: (a) => a.lastInspection,
    },

    {
      key: "category",
      header: "Carbon category",
      sortable: true,
      value: (a) => a.carbonCategory,
    },
  ];

  const save = async () => {
  if (!editing) return;

  const isNew = !editing.id;

  if (isNew && !canCreateAsset) {
    toast.error(
      "You do not have permission to create assets.",
    );
    return;
  }

  if (!isNew && !canEditAsset) {
    toast.error(
      "You do not have permission to edit assets.",
    );
    return;
  }

  const e: FieldErrors = {};

  if (!editing.name.trim()) {
    e.name = "Asset name is required.";
  }

  if (!editing.capacity.trim()) {
    e.capacity =
      "Rated capacity is required.";
  }

  if (
    editing.operatingHours < 0 ||
    editing.operatingHours > 744
  ) {
    e.operatingHours =
      "Operating hours must be between 0 and 744.";
  }

  setErrors(e);

  if (Object.keys(e).length > 0) {
    return;
  }

  const facility = facilities.find(
    (f) =>
      f.facilityId === editing.facilityId,
  );

  if (!facility) {
    toast.error(
      "Selected facility could not be found.",
    );
    return;
  }

  setAssetSaving(true);

  try {
    const assetId =
      editing.id ||
      `${facility.code}-AST-${Math.floor(
        Math.random() * 800 + 200,
      )}`;

    if (isNew) {
      await createAsset.mutateAsync({
          id: assetId,
          facilityId:
            editing.facilityId,
          name: editing.name.trim(),
          unit: editing.unit,
          type: editing.type,
          status: editing.status,
          energySource:
            editing.energySource,
          operatingHours:
            editing.operatingHours,
          engineer: editing.engineer,
          lastInspection:
            editing.lastInspection,
          carbonCategory:
            editing.carbonCategory,
          emissionSourceType:
            editing.emissionSourceType,
          capacity:
            editing.capacity.trim(),
        });

      toast.success(
        `Asset ${assetId} created`,
        {
          description:
            `${editing.name} · ${facility.name}`,
        },
      );
    } else {
      await updateAsset.mutateAsync({
        id: editing.id,
        changes: {
            facilityId:
              editing.facilityId,
            name: editing.name.trim(),
            unit: editing.unit,
            type: editing.type,
            status: editing.status,
            energySource:
              editing.energySource,
            operatingHours:
              editing.operatingHours,
            engineer: editing.engineer,
            lastInspection:
              editing.lastInspection,
            carbonCategory:
              editing.carbonCategory,
            emissionSourceType:
              editing.emissionSourceType,
            capacity:
              editing.capacity.trim(),
          },
      });

      toast.success(
        `Asset ${editing.id} updated`,
        {
          description:
            `${editing.name} · ${facility.name}`,
        },
      );
    }

    setEditing(null);

    // the mutation already refetched the affected queries
  } catch (error) {
    console.error(
      "Asset save failed:",
      error,
    );

    toast.error(
      isNew
        ? "Failed to create asset"
        : "Failed to update asset",
      {
        description:
          error instanceof Error
            ? error.message
            : "An unexpected error occurred.",
      },
    );
  } finally {
    setAssetSaving(false);
  }
};

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Operations"
        title="Facilities & Assets"
        description="Organisational hierarchy and emission-source inventory. Assets drive activity data collection, energy metering and Scope 1/2 boundary definition."
        actions={
          role === "Administrator" && (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
  variant="outline"
  onClick={openCreateFacility}
>
  <Plus className="size-4" />
  Create Facility
</Button>

              <Button
                onClick={() => {
                  setEditing(emptyAsset(facilities));
                  setErrors({});
                }}
              >
                <Plus className="size-4" />
                Create Asset
              </Button>
            </div>
          )
        }
      />

      <Tabs defaultValue="inventory">
        <TabsList>
          <TabsTrigger value="inventory">
            Asset inventory
          </TabsTrigger>

          <TabsTrigger value="hierarchy">
            Facility hierarchy
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="inventory"
          className="space-y-4 pt-4"
        >
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Total assets"
              value={assets.length}
              hint={`Across ${facilities.length} facilities`}
              icon={
                <Building2 className="size-4" />
              }
            />

            <StatCard
              label="Operational"
              value={
                assets.filter(
                  (a) => a.status === "Operational",
                ).length
              }
              hint="Reporting live data"
              tone="success"
            />

            <StatCard
              label="Under maintenance"
              value={
                assets.filter(
                  (a) =>
                    a.status === "Under Maintenance",
                ).length
              }
              hint="Partial period data expected"
              tone="warning"
            />

            <StatCard
              label="Scope 1 sources"
              value={
                assets.filter(
                  (a) =>
                    a.carbonCategory === "Scope 1",
                ).length
              }
              hint="Direct emission sources"
              tone="info"
            />
          </div>

          <DataTable
            data={rows}
            columns={columns}
            rowKey={(a) => a.id}
            searchKeys={(a) =>
              `${a.id} ${a.name} ${a.type} ${a.engineer} ${a.unit}`
            }
            searchPlaceholder="Search asset ID, name, type or engineer…"
            onRowClick={setDetail}
            pageSize={8}
            toolbar={
              <>
                <Select
                  value={facilityFilter}
                  onValueChange={setFacilityFilter}
                >
                  <SelectTrigger className="h-9 w-52">
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    <SelectItem value="all">
                      All facilities
                    </SelectItem>

                    {facilities.map((f) => (
                      <SelectItem
                        key={f.facilityId}
                        value={f.facilityId}
                      >
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select
                  value={statusFilter}
                  onValueChange={setStatusFilter}
                >
                  <SelectTrigger className="h-9 w-48">
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    <SelectItem value="all">
                      All statuses
                    </SelectItem>

                    {[
                      "Operational",
                      "Under Maintenance",
                      "Standby",
                      "Shutdown",
                    ].map((s) => (
                      <SelectItem
                        key={s}
                        value={s}
                      >
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            }
            actions={(a) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Row actions"
                  >
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end">
  <DropdownMenuItem
    onClick={() => setDetail(a)}
  >
    <Eye className="size-4" />
    View details
  </DropdownMenuItem>

  {canEditAsset && (
    <DropdownMenuItem
      onClick={() => {
        setEditing(a);
        setErrors({});
      }}
    >
      <Pencil className="size-4" />
      Edit asset
    </DropdownMenuItem>
  )}

  {canDeleteAsset && (
    <DropdownMenuItem
      className="text-destructive focus:text-destructive"
      onClick={() => setDeleting(a)}
    >
      <Trash2 className="size-4" />
      Delete asset
    </DropdownMenuItem>
  )}
</DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>

        <TabsContent
  value="hierarchy"
  className="pt-4"
>
  <div className="grid gap-4 md:grid-cols-2">
    {facilities.map((f) => (
      <SectionCard
        key={f.facilityId}
        title={f.name}
        description={`${f.type} · ${f.region} · commissioned ${f.commissioned}`}
      >
        <div className="grid grid-cols-2 gap-3 pb-3">
          <Field
            label="Facility code"
            value={f.code}
          />

          <Field
            label="Asset manager"
            value={f.manager}
          />

          <Field
            label="Head count"
            value={f.employees.toLocaleString(
              "en-IN",
            )}
          />

          <Field
            label="Assets registered"
            value={
              assets.filter(
                (a) =>
                  a.facilityId ===
                  f.facilityId,
              ).length
            }
          />
        </div>

        <div className="space-y-3 border-t border-border pt-3">
          {f.units.map((u) => (
            <div key={u}>
              <p className="text-sm font-medium">
                {u}
              </p>

              <ul className="mt-1 space-y-1 border-l border-border pl-3">
                {assets
                  .filter(
                    (a) =>
                      a.facilityId ===
                        f.facilityId &&
                      a.unit === u,
                  )
                  .map((a) => (
                    <li
                      key={a.id}
                      className="flex items-center justify-between gap-2 text-xs"
                    >
                      <button
                        className="truncate text-left hover:text-primary"
                        onClick={() =>
                          setDetail(a)
                        }
                      >
                        {a.name}{" "}
                        <span className="text-muted-foreground">
                          ({a.type})
                        </span>
                      </button>

                      <StatusBadge
                        value={a.status}
                      />
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>

        {role === "Administrator" && (
          <div className="mt-4 flex gap-2 border-t border-border pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                openEditFacility(f)
              }
            >
              <Pencil className="size-4" />
              Edit Facility
            </Button>

            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() =>
                setFacilityToDelete(f)
              }
            >
              <Trash2 className="size-4" />
              Delete Facility
            </Button>
          </div>
        )}
      </SectionCard>
    ))}
  </div>
</TabsContent>
      </Tabs>

      <Sheet
        open={!!detail}
        onOpenChange={(o) =>
          !o && setDetail(null)
        }
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>
                  {detail.name}
                </SheetTitle>

                <SheetDescription>
                  {detail.id} ·{" "}
                  {facilityName(
                    detail.facilityId,
                  )}{" "}
                  · {detail.unit}
                </SheetDescription>
              </SheetHeader>

              <div className="space-y-6 px-4 pb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field
                    label="Asset type"
                    value={detail.type}
                  />

                  <Field
                    label="Operational status"
                    value={
                      <StatusBadge
                        value={detail.status}
                      />
                    }
                  />

                  <Field
                    label="Energy source"
                    value={detail.energySource}
                  />

                  <Field
                    label="Rated capacity"
                    value={detail.capacity}
                  />

                  <Field
                    label="Operating hours (period)"
                    value={`${detail.operatingHours} h`}
                  />

                  <Field
                    label="Assigned engineer"
                    value={detail.engineer}
                  />

                  <Field
                    label="Last inspection"
                    value={detail.lastInspection}
                  />

                  <Field
                    label="Carbon category"
                    value={detail.carbonCategory}
                  />

                  <Field
                    label="Emission source type"
                    value={detail.emissionSourceType}
                  />
                </div>

                <SectionCard
                  title="Related submissions"
                  description="Activity data periods covering this asset's unit"
                >
                  <ul className="space-y-2">
                    {submissions
                      .filter(
                        (s) =>
                          s.facilityId ===
                          detail.facilityId,
                      )
                      .slice(0, 5)
                      .map((s) => (
                        <li
                          key={s.id}
                          className="flex items-center justify-between gap-2 text-sm"
                        >
                          <span className="tabular">
                            {s.id}
                          </span>

                          <span className="text-xs text-muted-foreground">
                            {s.month}
                          </span>

                          <StatusBadge
                            value={s.status}
                          />
                        </li>
                      ))}
                  </ul>
                </SectionCard>

                <div className="flex gap-2">
                  {canEditAsset && (
  <Button
    onClick={() => {
      setEditing(detail);
      setDetail(null);
    }}
  >
    <Pencil className="size-4" />
    Edit asset
  </Button>
)}

                  <Button
                    variant="outline"
                    onClick={() =>
                      setDetail(null)
                    }
                  >
                    Close
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <Dialog
        open={!!editing}
        onOpenChange={(o) =>
          !o && setEditing(null)
        }
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editing?.id
                ? `Edit ${editing.id}`
                : "Create asset"}
            </DialogTitle>

            <DialogDescription>
              Assets define the Scope 1 and Scope 2
              emission-source boundary for each
              facility.
            </DialogDescription>
          </DialogHeader>

          {editing ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="a-name">
                  Asset name
                </Label>

                <Input
                  id="a-name"
                  value={editing.name}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      name: e.target.value,
                    })
                  }
                  placeholder="e.g. HZR Boiler B2"
                />

                {errors.name ? (
                  <p className="text-xs text-destructive">
                    {errors.name}
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label>Facility</Label>

                <Select
                  value={editing.facilityId}
                  onValueChange={(v) =>
                    setEditing({
                      ...editing,
                      facilityId: v,
                      unit:
                        facilities.find(
                          (f) =>
                            f.facilityId === v,
                        )?.units[0] ?? "",
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    {facilities.map((f) => (
                      <SelectItem
                        key={f.facilityId}
                        value={f.facilityId}
                      >
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Production unit</Label>

                <Select
                  value={editing.unit}
                  onValueChange={(v) =>
                    setEditing({
                      ...editing,
                      unit: v,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    {(
                      facilities.find(
                        (f) =>
                          f.facilityId ===
                          editing.facilityId,
                      )?.units ?? []
                    ).map((u) => (
                      <SelectItem
                        key={u}
                        value={u}
                      >
                        {u}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Asset type</Label>

                <Select
                  value={editing.type}
                  onValueChange={(v) =>
                    setEditing({
                      ...editing,
                      type: v,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    {assetTypes.map((t) => (
                      <SelectItem
                        key={t}
                        value={t}
                      >
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>
                  Operational status
                </Label>

                <Select
                  value={editing.status}
                  onValueChange={(v) =>
                    setEditing({
                      ...editing,
                      status:
                        v as Asset["status"],
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    {[
                      "Operational",
                      "Under Maintenance",
                      "Standby",
                      "Shutdown",
                    ].map((s) => (
                      <SelectItem
                        key={s}
                        value={s}
                      >
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-energy">
                  Energy source
                </Label>

                <Input
                  id="a-energy"
                  value={editing.energySource}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      energySource:
                        e.target.value,
                    })
                  }
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-cap">
                  Rated capacity
                </Label>

                <Input
                  id="a-cap"
                  value={editing.capacity}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      capacity: e.target.value,
                    })
                  }
                  placeholder="e.g. 120 TPH"
                />

                {errors.capacity ? (
                  <p className="text-xs text-destructive">
                    {errors.capacity}
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-hours">
                  Operating hours
                </Label>

                <Input
                  id="a-hours"
                  type="number"
                  value={editing.operatingHours}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      operatingHours:
                        Number(e.target.value),
                    })
                  }
                />

                {errors.operatingHours ? (
                  <p className="text-xs text-destructive">
                    {errors.operatingHours}
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-eng">
                  Assigned engineer
                </Label>

                <Input
                  id="a-eng"
                  value={editing.engineer}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      engineer: e.target.value,
                    })
                  }
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-insp">
                  Last inspection date
                </Label>

                <Input
                  id="a-insp"
                  type="date"
                  value={editing.lastInspection}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      lastInspection:
                        e.target.value,
                    })
                  }
                />
              </div>

              <div className="space-y-1.5">
                <Label>
                  Carbon category
                </Label>

                <Select
                  value={editing.carbonCategory}
                  onValueChange={(v) =>
                    setEditing({
                      ...editing,
                      carbonCategory: v,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>

                  <SelectContent>
                    {[
                      "Scope 1",
                      "Scope 2",
                      "Scope 3",
                    ].map((s) => (
                      <SelectItem
                        key={s}
                        value={s}
                      >
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="a-src">
                  Emission source type
                </Label>

                <Input
                  id="a-src"
                  value={editing.emissionSourceType}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      emissionSourceType:
                        e.target.value,
                    })
                  }
                />
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() =>
                setEditing(null)
              }
            >
              Cancel
            </Button>

          <Button
  disabled={assetSaving}
  onClick={save}
>
  {assetSaving
    ? "Saving..."
    : "Save asset"}
</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
  open={facilityDialogOpen}
  onOpenChange={(open) => {
    if (!facilitySaving) {
      setFacilityDialogOpen(open);

      if (!open) {
        setFacilityBeingEdited(null);
      }
    }
  }}
>
  <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
    <DialogHeader>
      <DialogTitle>
        {facilityBeingEdited
          ? `Edit ${facilityBeingEdited.name}`
          : "Create facility"}
      </DialogTitle>

      <DialogDescription>
        Manage the facility master record stored in
        MongoDB.
      </DialogDescription>
    </DialogHeader>

    <div className="grid gap-4 sm:grid-cols-2">
      {!facilityBeingEdited && (
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="facility-id">
            Facility ID
          </Label>

          <Input
            id="facility-id"
            value={facilityForm.facilityId}
            onChange={(e) =>
              setFacilityForm({
                ...facilityForm,
                facilityId: e.target.value,
              })
            }
            placeholder="e.g. FAC-HZR"
          />

          <p className="text-xs text-muted-foreground">
            Leave blank to generate an ID
            automatically.
          </p>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="facility-name">
          Facility name
        </Label>

        <Input
          id="facility-name"
          value={facilityForm.name}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              name: e.target.value,
            })
          }
          placeholder="e.g. Hazira Processing Complex"
        />

        {facilityErrors.name && (
          <p className="text-xs text-destructive">
            {facilityErrors.name}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="facility-code">
          Facility code
        </Label>

        <Input
          id="facility-code"
          value={facilityForm.code}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              code: e.target.value,
            })
          }
          placeholder="e.g. HZR"
        />

        {facilityErrors.code && (
          <p className="text-xs text-destructive">
            {facilityErrors.code}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="facility-region">
          Region
        </Label>

        <Input
          id="facility-region"
          value={facilityForm.region}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              region: e.target.value,
            })
          }
          placeholder="e.g. Gujarat"
        />

        {facilityErrors.region && (
          <p className="text-xs text-destructive">
            {facilityErrors.region}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Facility type</Label>

        <Select
          value={facilityForm.type}
          onValueChange={(value) =>
            setFacilityForm({
              ...facilityForm,
              type: value,
            })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>

          <SelectContent>
            {[
              "Production Facility",
              "Processing Facility",
              "Refinery",
              "Offshore Platform",
              "Pipeline Facility",
              "Storage Facility",
              "Gas Processing Plant",
              "Terminal",
              "Other",
            ].map((type) => (
              <SelectItem
                key={type}
                value={type}
              >
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="facility-manager">
          Facility manager
        </Label>

        <Input
          id="facility-manager"
          value={facilityForm.manager}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              manager: e.target.value,
            })
          }
          placeholder="e.g. R. Sharma"
        />

        {facilityErrors.manager && (
          <p className="text-xs text-destructive">
            {facilityErrors.manager}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="facility-employees">
          Employees
        </Label>

        <Input
          id="facility-employees"
          type="number"
          min={0}
          value={facilityForm.employees}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              employees: Number(e.target.value),
            })
          }
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="facility-commissioned">
          Commissioned date
        </Label>

        <Input
          id="facility-commissioned"
          type="date"
          value={facilityForm.commissioned}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              commissioned: e.target.value,
            })
          }
        />

        {facilityErrors.commissioned && (
          <p className="text-xs text-destructive">
            {facilityErrors.commissioned}
          </p>
        )}
      </div>

      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="facility-units">
          Production units
        </Label>

        <Input
          id="facility-units"
          value={facilityForm.units}
          onChange={(e) =>
            setFacilityForm({
              ...facilityForm,
              units: e.target.value,
            })
          }
          placeholder="e.g. CDU, VDU, Gas Processing"
        />

        <p className="text-xs text-muted-foreground">
          Enter units separated by commas.
        </p>
      </div>
    </div>

    <DialogFooter>
      <Button
        variant="outline"
        disabled={facilitySaving}
        onClick={() =>
          setFacilityDialogOpen(false)
        }
      >
        Cancel
      </Button>

      <Button
        disabled={facilitySaving}
        onClick={saveFacility}
      >
        {facilitySaving
          ? "Saving..."
          : facilityBeingEdited
            ? "Save changes"
            : "Create facility"}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

      <AlertDialog
        open={!!deleting}
        onOpenChange={(o) =>
          !o && setDeleting(null)
        }
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete {deleting?.id}?
            </AlertDialogTitle>

            <AlertDialogDescription>
              This removes the asset from the
              emission-source boundary. Historical
              submissions remain, but future periods
              will exclude this source.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <AlertDialogFooter>
            <AlertDialogCancel>
              Cancel
            </AlertDialogCancel>

            <AlertDialogAction
  disabled={assetDeleting}
  onClick={async (event) => {
    event.preventDefault();

    if (!deleting) {
      return;
    }

    if (!canDeleteAsset) {
      toast.error(
        "You do not have permission to delete assets.",
      );

      setDeleting(null);
      return;
    }

    setAssetDeleting(true);

    try {
      await deleteAsset.mutateAsync(deleting.id);

      toast.success(
        `Asset ${deleting.id} deleted`,
      );

      setDeleting(null);

      // the mutation already refetched the affected queries
    } catch (error) {
      console.error(
        "Asset delete failed:",
        error,
      );

      toast.error(
        "Failed to delete asset",
        {
          description:
            error instanceof Error
              ? error.message
              : "An unexpected error occurred.",
        },
      );
    } finally {
      setAssetDeleting(false);
    }
  }}
>
  {assetDeleting
    ? "Deleting..."
    : "Delete asset"}
</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
  open={!!facilityToDelete}
  onOpenChange={(open) => {
    if (!facilityDeleting && !open) {
      setFacilityToDelete(null);
    }
  }}
>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>
        Delete {facilityToDelete?.name}?
      </AlertDialogTitle>

      <AlertDialogDescription>
        This will permanently remove the facility
        master record from MongoDB.

        {facilityToDelete && (
          <>
            {" "}
            The facility currently has{" "}
            <strong>
              {
                assets.filter(
                  (a) =>
                    a.facilityId ===
                    facilityToDelete.facilityId,
                ).length
              }
            </strong>{" "}
            registered asset(s).
          </>
        )}
      </AlertDialogDescription>
    </AlertDialogHeader>

    <AlertDialogFooter>
      <AlertDialogCancel
        disabled={facilityDeleting}
      >
        Cancel
      </AlertDialogCancel>

      <AlertDialogAction
        disabled={facilityDeleting}
        onClick={(event) => {
          event.preventDefault();
          void confirmDeleteFacility();
        }}
        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
      >
        {facilityDeleting
          ? "Deleting..."
          : "Delete facility"}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
    </div>
  );
}