import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ScanLine, Loader2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect } from "@/components/common";

const EMPTY = { client_id: "", vin: "", plate: "", make: "", model: "", year: "", engine: "", power_kw: "", euro: "6", fuel: "diesel",
  mileage: 0, color: "", itp_expiry: "", rca_expiry: "", casco_expiry: "", rovinieta_expiry: "" };
const FUELS = ["benzina", "diesel", "hibrid", "electric", "gpl"];
const OTHER = "__other";

function ListSelect({ label, options, value, onChange, disabled, testid }) {
  const { tr } = useLang();
  const [custom, setCustom] = useState(false);
  const opts = value && !options.includes(value) ? [value, ...options] : options;
  return (
    <Field label={label}>
      {custom ? (
        <div className="flex gap-1">
          <Input data-testid={`${testid}-custom-input`} autoFocus value={value} onChange={(e) => onChange(e.target.value)} />
          <Button type="button" variant="outline" size="sm" onClick={() => setCustom(false)}>↺</Button>
        </div>
      ) : (
        <NativeSelect data-testid={testid} value={value} disabled={disabled}
          onChange={(e) => (e.target.value === OTHER ? (setCustom(true), onChange("")) : onChange(e.target.value))}>
          <option value="">—</option>
          {opts.map((o) => <option key={o} value={o}>{o}</option>)}
          <option value={OTHER}>{tr("Altul (introducere manuală)…", "Other (type manually)…")}</option>
        </NativeSelect>
      )}
    </Field>
  );
}

function useVinDecode(f, setF, enabled) {
  const [state, setState] = useState(null);
  const decode = useCallback(async (vin) => {
    setState({ loading: true });
    try {
      const { data } = await api.get(`/vin/decode/${encodeURIComponent(vin)}`);
      setF((p) => ({
        ...p,
        make: data.make || p.make,
        model: data.model || (data.make && data.make !== p.make ? "" : p.model),
        year: data.year || p.year,
        engine: data.engine || p.engine,
        power_kw: data.power_kw || p.power_kw,
        fuel: data.fuel || p.fuel,
      }));
      setState(data);
    } catch (e) {
      setState({ error: errMsg(e) });
    }
  }, [setF]);

  useEffect(() => {
    if (enabled && f.vin.length === 17) decode(f.vin);
  }, [decode, enabled, f.vin]);
  return { state, decode };
}

function DecodeInfo({ state }) {
  const { tr } = useLang();
  if (!state) return null;
  if (state.loading) return <div className="flex items-center gap-1 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" />{tr("Decodare VIN…", "Decoding VIN…")}</div>;
  if (state.error) return <div className="text-xs text-rose-500">{state.error}</div>;
  const filled = ["make", "model", "year", "engine", "power_kw", "fuel"].filter((k) => state[k]);
  const names = { make: tr("marcă", "make"), model: "model", year: tr("an", "year"), engine: tr("motor", "engine"), power_kw: tr("putere", "power"), fuel: tr("combustibil", "fuel") };
  return (
    <div data-testid="vin-decode-result" className="rounded border border-cyan-500/30 bg-cyan-500/5 px-3 py-2 text-xs">
      <span className="font-semibold text-cyan-600 dark:text-cyan-400">{tr("VIN decodat", "VIN decoded")} ({state.source === "nhtsa" ? "NHTSA vPIC" : "WMI"})</span>
      {" · "}{filled.length ? `${tr("completat", "filled")}: ${filled.map((k) => names[k]).join(", ")}` : tr("nicio informație găsită — completați manual", "nothing found — fill manually")}
      {state.warnings?.map((w) => <div key={w} className="text-yellow-600 dark:text-yellow-400">{w}</div>)}
      {state.exists && <div className="text-rose-500">{tr("Atenție: VIN deja înregistrat în sistem", "Warning: VIN already registered")}</div>}
      {filled.length > 0 && <div className="text-muted-foreground">{tr("Verificați datele completate automat.", "Please verify auto-filled data.")}</div>}
    </div>
  );
}

export default function VehicleForm({ open, onOpenChange, initial, clientId, onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState(EMPTY);
  const { data: clients } = useApi(open && !clientId ? "/clients" : null);
  const { data: catalog } = useApi(open ? "/vehicle-catalog" : null);
  const isNew = !initial?.id;
  const { state, decode } = useVinDecode(f, setF, open && isNew);
  useEffect(() => {
    if (open) setF({ ...EMPTY, ...(initial || {}), client_id: initial?.client_id || clientId || "" });
  }, [open, initial, clientId]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const makes = Object.keys(catalog?.makes || {});
  const models = catalog?.makes?.[f.make] || [];

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
          <Field label="VIN / serie șasiu" className="sm:col-span-2">
            <div className="flex gap-1">
              <Input data-testid="vehicle-vin-input" className="font-mono uppercase" maxLength={17} value={f.vin}
                onChange={(e) => setF({ ...f, vin: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} />
              <Button type="button" variant="outline" size="icon" data-testid="vehicle-vin-decode-button" title={tr("Decodează VIN", "Decode VIN")}
                disabled={f.vin.length !== 17} onClick={() => decode(f.vin)}><ScanLine className="h-4 w-4" /></Button>
            </div>
            <span className="font-mono text-[10px] text-muted-foreground">{f.vin.length}/17</span>
          </Field>
          <Field label={tr("Nr. înmatriculare", "Plate")}><Input data-testid="vehicle-plate-input" className="font-mono uppercase" value={f.plate} onChange={set("plate")} /></Field>
          <div className="sm:col-span-3"><DecodeInfo state={state} /></div>
          <ListSelect label={tr("Marcă", "Make")} testid="vehicle-make-select" options={makes} value={f.make}
            onChange={(v) => setF((p) => ({ ...p, make: v, model: v === p.make ? p.model : "" }))} />
          <ListSelect key={f.make} label="Model" testid="vehicle-model-select" options={models} value={f.model}
            onChange={(v) => setF((p) => ({ ...p, model: v }))} />
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
          <Button data-testid="vehicle-save-button" onClick={save} disabled={!f.client_id || !f.vin || !f.plate || !f.make || !f.model}>{tr("Salvează", "Save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
