import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Plus, Check } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { PageHeader, Panel, Field, NativeSelect } from "@/components/common";
import PhotoSlot from "@/components/PhotoSlot";
import SignaturePad from "@/components/SignaturePad";
import ClientForm from "@/components/ClientForm";
import VehicleForm from "@/components/VehicleForm";

const PHOTOS = [["front", "Față", "Front"], ["back", "Spate", "Rear"], ["left", "Lateral stânga", "Left side"], ["right", "Lateral dreapta", "Right side"], ["interior", "Interior / bord", "Interior / dash"]];
const ACCESSORIES = [["Roată rezervă", "Spare wheel"], ["Trusă medicală", "First-aid kit"], ["Triunghi", "Warning triangle"], ["Extinctor", "Extinguisher"], ["Cric", "Jack"], ["Talon / acte", "Registration docs"], ["Cheie rezervă", "Spare key"]];
const FUEL = ["0", "1/4", "1/2", "3/4", "1/1"];

function Steps({ step, labels }) {
  return (
    <div className="mb-6 grid grid-cols-4 gap-2">
      {labels.map((l, i) => (
        <div key={l} className={`border-t-2 pt-2 text-xs font-semibold uppercase tracking-wider ${i <= step ? "border-primary text-foreground" : "border-border text-muted-foreground"}`}>
          <span className="font-mono">0{i + 1}</span> · {l}
        </div>
      ))}
    </div>
  );
}

export default function Reception() {
  const { tr } = useLang();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [f, setF] = useState({ client_id: "", vehicle_id: "", mileage_in: "", fuel_level: "1/2", complaint: "", observations: "", accessories: [], damages: "", elevator: "", promised_date: "", photos: {}, signature: "" });
  const [dlg, setDlg] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: clients, reload: reloadC } = useApi("/clients");
  const { data: vehicles, reload: reloadV } = useApi(f.client_id ? `/vehicles?client_id=${f.client_id}` : null, [f.client_id]);
  const { data: settings } = useApi("/settings");
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const vehicle = (vehicles || []).find((v) => v.id === f.vehicle_id);

  const valid = [
    f.client_id && f.vehicle_id,
    f.mileage_in && f.complaint,
    PHOTOS.every(([k]) => f.photos[k]),
    !!f.signature,
  ];

  const submit = async () => {
    setBusy(true);
    try {
      const body = { ...f, mileage_in: Number(f.mileage_in), damages: f.damages ? f.damages.split("\n").filter(Boolean) : [] };
      const r = await api.post("/work-orders", body);
      toast.success(`${tr("Comandă creată", "Order created")} ${r.data.number}`);
      nav(`/work-orders/${r.data.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const labels = [tr("Client & vehicul", "Client & vehicle"), tr("Constatare", "Inspection"), tr("Fotografii", "Photos"), tr("Semnătură", "Signature")];
  return (
    <div data-testid="reception-page" className="mx-auto max-w-5xl">
      <PageHeader eyebrow={tr("Notă recepție · fișă intrare · PV predare-primire", "Reception note · check-in sheet · handover")} title={tr("Recepție vehicul", "Vehicle reception")} />
      <Steps step={step} labels={labels} />
      <Panel>
        {step === 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={tr("Client", "Client")}>
              <div className="flex gap-2">
                <NativeSelect data-testid="reception-client-select" value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value, vehicle_id: "" })}>
                  <option value="">—</option>
                  {(clients || []).map((c) => <option key={c.id} value={c.id}>{c.name} {c.cui || ""}</option>)}
                </NativeSelect>
                <Button variant="outline" size="icon" data-testid="reception-new-client-button" onClick={() => setDlg("client")}><Plus className="h-4 w-4" /></Button>
              </div>
            </Field>
            <Field label={tr("Vehicul", "Vehicle")}>
              <div className="flex gap-2">
                <NativeSelect data-testid="reception-vehicle-select" value={f.vehicle_id} disabled={!f.client_id}
                  onChange={(e) => { const v = (vehicles || []).find((x) => x.id === e.target.value); setF({ ...f, vehicle_id: e.target.value, mileage_in: v?.mileage || "" }); }}>
                  <option value="">—</option>
                  {(vehicles || []).map((v) => <option key={v.id} value={v.id}>{v.plate} · {v.make} {v.model}</option>)}
                </NativeSelect>
                <Button variant="outline" size="icon" disabled={!f.client_id} data-testid="reception-new-vehicle-button" onClick={() => setDlg("vehicle")}><Plus className="h-4 w-4" /></Button>
              </div>
            </Field>
            {vehicle && (
              <div className="rounded border bg-muted/40 p-3 font-mono text-xs sm:col-span-2">VIN {vehicle.vin} · {vehicle.engine} · {vehicle.power_kw} kW · {vehicle.fuel} · Euro {vehicle.euro} · {vehicle.mileage} km</div>
            )}
          </div>
        )}
        {step === 1 && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={tr("Kilometraj intrare", "Mileage in")}><Input data-testid="reception-mileage-input" type="number" value={f.mileage_in} onChange={set("mileage_in")} /></Field>
            <Field label={tr("Nivel combustibil", "Fuel level")}>
              <NativeSelect data-testid="reception-fuel-select" value={f.fuel_level} onChange={set("fuel_level")}>{FUEL.map((x) => <option key={x}>{x}</option>)}</NativeSelect>
            </Field>
            <Field label={tr("Elevator", "Lift")}>
              <NativeSelect data-testid="reception-elevator-select" value={f.elevator} onChange={set("elevator")}>
                <option value="">—</option>{(settings?.elevators || []).map((x) => <option key={x}>{x}</option>)}
              </NativeSelect>
            </Field>
            <Field label={tr("Solicitare client / simptome", "Customer complaint / symptoms")} className="sm:col-span-3">
              <Textarea data-testid="reception-complaint-input" rows={3} value={f.complaint} onChange={set("complaint")} />
            </Field>
            <Field label={tr("Daune existente (câte una pe rând)", "Existing damage (one per line)")} className="sm:col-span-2">
              <Textarea data-testid="reception-damages-input" rows={3} value={f.damages} onChange={set("damages")} placeholder={tr("ex. Zgârietură bară față dreapta", "e.g. Scratch front bumper right")} />
            </Field>
            <Field label={tr("Termen promis", "Promised date")}><Input data-testid="reception-promised-input" type="date" value={f.promised_date} onChange={set("promised_date")} /></Field>
            <div className="sm:col-span-3">
              <div className="eyebrow mb-2">{tr("Accesorii predate", "Accessories handed over")}</div>
              <div className="flex flex-wrap gap-4">
                {ACCESSORIES.map(([ro, en]) => (
                  <label key={ro} className="flex items-center gap-2 text-sm">
                    <Checkbox data-testid={`reception-acc-${ro}`} checked={f.accessories.includes(ro)}
                      onCheckedChange={(c) => setF({ ...f, accessories: c ? [...f.accessories, ro] : f.accessories.filter((a) => a !== ro) })} />
                    {tr(ro, en)}
                  </label>
                ))}
              </div>
            </div>
            <Field label={tr("Observații", "Notes")} className="sm:col-span-3"><Textarea rows={2} value={f.observations} onChange={set("observations")} /></Field>
          </div>
        )}
        {step === 2 && (
          <div>
            <p className="mb-4 text-sm text-muted-foreground">{tr("Toate cele 5 fotografii sunt obligatorii.", "All 5 photos are mandatory.")}</p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {PHOTOS.map(([k, ro, en]) => <PhotoSlot key={k} testid={`reception-photo-${k}`} label={tr(ro, en)} value={f.photos[k]} onChange={(v) => setF({ ...f, photos: { ...f.photos, [k]: v } })} />)}
            </div>
          </div>
        )}
        {step === 3 && (
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2 text-sm">
              <div className="eyebrow">{tr("Sumar", "Summary")}</div>
              <div>{(clients || []).find((c) => c.id === f.client_id)?.name}</div>
              <div className="font-mono text-xs">{vehicle?.plate} · {vehicle?.make} {vehicle?.model} · {f.mileage_in} km · {tr("combustibil", "fuel")} {f.fuel_level}</div>
              <div className="text-muted-foreground">{f.complaint}</div>
              <p className="pt-2 text-xs text-muted-foreground">{tr("Prin semnare, clientul confirmă predarea vehiculului în starea descrisă și acordul pentru diagnosticare.",
                "By signing, the customer confirms handing over the vehicle in the described condition and agrees to diagnostics.")}</p>
            </div>
            <div>
              <div className="eyebrow mb-2">{tr("Semnătură client", "Customer signature")}</div>
              <SignaturePad testid="reception-signature-pad" value={f.signature} onChange={set("signature")} />
            </div>
          </div>
        )}
        <div className="mt-6 flex justify-between border-t pt-4">
          <Button variant="outline" disabled={step === 0} onClick={() => setStep(step - 1)} data-testid="reception-prev-button"><ChevronLeft className="mr-1 h-4 w-4" />{tr("Înapoi", "Back")}</Button>
          {step < 3 ? (
            <Button disabled={!valid[step]} onClick={() => setStep(step + 1)} data-testid="reception-next-button">{tr("Continuă", "Next")}<ChevronRight className="ml-1 h-4 w-4" /></Button>
          ) : (
            <Button disabled={!valid.every(Boolean) || busy} onClick={submit} data-testid="reception-submit-button"><Check className="mr-1 h-4 w-4" />{tr("Creează comanda de lucru", "Create work order")}</Button>
          )}
        </div>
      </Panel>
      <ClientForm open={dlg === "client"} onOpenChange={(o) => !o && setDlg("")} onSaved={(c) => { reloadC(); setF({ ...f, client_id: c.id, vehicle_id: "" }); }} />
      <VehicleForm open={dlg === "vehicle"} onOpenChange={(o) => !o && setDlg("")} clientId={f.client_id}
        onSaved={(v) => { reloadV(); setF({ ...f, vehicle_id: v.id, mileage_in: v.mileage }); }} />
    </div>
  );
}
