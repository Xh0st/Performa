import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect } from "@/components/common";

const EMPTY = { client_id: "", vin: "", plate: "", make: "", model: "", year: "", engine: "", power_kw: "", euro: "6", fuel: "diesel",
  mileage: 0, color: "", itp_expiry: "", rca_expiry: "", casco_expiry: "", rovinieta_expiry: "" };
const FUELS = ["benzina", "diesel", "hibrid", "electric", "gpl"];

export default function VehicleForm({ open, onOpenChange, initial, clientId, onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState(EMPTY);
  const { data: clients } = useApi(open && !clientId ? "/clients" : null);
  useEffect(() => {
    if (open) setF({ ...EMPTY, ...(initial || {}), client_id: initial?.client_id || clientId || "" });
  }, [open, initial, clientId]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = async () => {
    try {
      const body = { ...f, year: f.year ? Number(f.year) : null, power_kw: f.power_kw ? Number(f.power_kw) : null, mileage: Number(f.mileage) || 0 };
      const r = initial?.id ? await api.put(`/vehicles/${initial.id}`, body) : await api.post("/vehicles", body);
      toast.success(tr("Vehicul salvat", "Vehicle saved"));
      onSaved?.(r.data);
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="vehicle-form-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{initial?.id ? tr("Editare vehicul", "Edit vehicle") : tr("Vehicul nou", "New vehicle")}</DialogTitle></DialogHeader>
        <div className="grid max-h-[65vh] gap-3 overflow-y-auto pr-1 sm:grid-cols-3">
          {!clientId && (
            <Field label={tr("Proprietar", "Owner")} className="sm:col-span-3">
              <NativeSelect data-testid="vehicle-client-select" value={f.client_id} onChange={set("client_id")}>
                <option value="">—</option>
                {(clients || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            </Field>
          )}
          <Field label="VIN / serie șasiu" className="sm:col-span-2"><Input data-testid="vehicle-vin-input" className="font-mono uppercase" maxLength={17} value={f.vin} onChange={set("vin")} /></Field>
          <Field label={tr("Nr. înmatriculare", "Plate")}><Input data-testid="vehicle-plate-input" className="font-mono uppercase" value={f.plate} onChange={set("plate")} /></Field>
          <Field label={tr("Marcă", "Make")}><Input data-testid="vehicle-make-input" value={f.make} onChange={set("make")} /></Field>
          <Field label="Model"><Input data-testid="vehicle-model-input" value={f.model} onChange={set("model")} /></Field>
          <Field label={tr("An fabricație", "Year")}><Input data-testid="vehicle-year-input" type="number" value={f.year ?? ""} onChange={set("year")} /></Field>
          <Field label={tr("Motorizare", "Engine")}><Input data-testid="vehicle-engine-input" value={f.engine} onChange={set("engine")} /></Field>
          <Field label={tr("Putere (kW)", "Power (kW)")}><Input data-testid="vehicle-power-input" type="number" value={f.power_kw ?? ""} onChange={set("power_kw")} /></Field>
          <Field label="Euro"><Input data-testid="vehicle-euro-input" value={f.euro} onChange={set("euro")} /></Field>
          <Field label={tr("Combustibil", "Fuel")}>
            <NativeSelect data-testid="vehicle-fuel-select" value={f.fuel} onChange={set("fuel")}>{FUELS.map((x) => <option key={x}>{x}</option>)}</NativeSelect>
          </Field>
          <Field label={tr("Kilometraj", "Mileage")}><Input data-testid="vehicle-mileage-input" type="number" value={f.mileage} onChange={set("mileage")} /></Field>
          <Field label={tr("Culoare", "Color")}><Input value={f.color} onChange={set("color")} /></Field>
          <Field label={tr("Expirare ITP", "ITP expiry")}><Input data-testid="vehicle-itp-input" type="date" value={f.itp_expiry} onChange={set("itp_expiry")} /></Field>
          <Field label={tr("Expirare RCA", "RCA expiry")}><Input data-testid="vehicle-rca-input" type="date" value={f.rca_expiry} onChange={set("rca_expiry")} /></Field>
          <Field label={tr("Expirare CASCO", "CASCO expiry")}><Input type="date" value={f.casco_expiry} onChange={set("casco_expiry")} /></Field>
          <Field label={tr("Expirare rovinietă", "Vignette expiry")}><Input type="date" value={f.rovinieta_expiry} onChange={set("rovinieta_expiry")} /></Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{tr("Anulează", "Cancel")}</Button>
          <Button data-testid="vehicle-save-button" onClick={save} disabled={!f.client_id || !f.vin || !f.plate}>{tr("Salvează", "Save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
