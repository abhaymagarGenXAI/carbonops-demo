import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAddProductionUnit } from "@/hooks/useApi";
type Fac = { id: string; name: string; units: string[] };

/** Administrator: adds one production unit to a facility. The unit goes into the facility master and the production-unit master. */
export function AddUnitDialog({ open, facilities, facilityId, onClose }: { open: boolean; facilities: Fac[]; facilityId?: string; onClose: () => void }) {
  const add = useAddProductionUnit();
  const [fid, setFid] = useState("");
  const [name, setName] = useState("");
  useEffect(() => {
    if (open) { setFid(facilityId ?? facilities[0]?.id ?? ""); setName(""); }
  }, [open, facilityId, facilities]);
  const facility = facilities.find((f) => f.id === fid);
  const clean = name.replace(/\s+/g, " ").trim();
  const duplicate = !!facility && facility.units.some((u) => u.toLowerCase() === clean.toLowerCase());
  const problem = !clean ? "" : clean.includes(",") ? "A unit name cannot contain a comma." : duplicate ? `${facility?.name} already has a unit called "${clean}".` : "";

  const save = async () => {
    try {
      await add.mutateAsync({ id: fid, name: clean });
      toast.success("Production unit added", { description: `${clean} · ${facility?.name}` });
      onClose();
    } catch (error) {
      toast.error("Could not add the unit", { description: error instanceof Error ? error.message : "Unexpected error" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !add.isPending && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add production unit</DialogTitle>
          <DialogDescription>The unit becomes selectable for assets and monthly activity data of that facility. Rename or removal of an unused unit is done under Edit Facility.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Facility</Label>
            <Select value={fid} onValueChange={setFid}>
              <SelectTrigger aria-label="Facility"><SelectValue placeholder="Select facility" /></SelectTrigger>
              <SelectContent>{facilities.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent>
            </Select>
            {facility?.units.length ? <p className="text-xs text-muted-foreground">Existing units: {facility.units.join(", ")}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="unit-name">Unit name</Label>
            <Input id="unit-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="e.g. Gas Compression Unit 2" />
            {problem ? <p className="text-xs text-destructive">{problem}</p> : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={add.isPending} onClick={onClose}>Cancel</Button>
          <Button disabled={add.isPending || !clean || !fid || !!problem} onClick={save}>{add.isPending ? "Adding…" : "Add unit"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
