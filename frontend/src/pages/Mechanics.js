import { useState } from "react";
import { toast } from "sonner";
import { LogIn, LogOut, Plus } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { useAuth } from "@/context/AuthContext";
import { num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PageHeader, Panel, Loading, LABOR_CATS, Field, NativeSelect } from "@/components/common";

const pctCls = (v) => (v >= 80 ? "text-emerald-500" : v >= 50 ? "text-yellow-500" : "text-rose-500");

function MechanicDialog({ open, onOpenChange, onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState({ name: "", specialty: "mecanic_senior", hourly_cost: 40, phone: "", bonus_pct: 0 });
  const save = async () => {
    try {
      await api.post("/mechanics", { ...f, hourly_cost: Number(f.hourly_cost), bonus_pct: Number(f.bonus_pct) });
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="mechanic-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Angajat nou", "New technician")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={tr("Nume", "Name")} className="sm:col-span-2"><Input data-testid="mechanic-name-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={tr("Specializare", "Specialty")}>
            <NativeSelect data-testid="mechanic-specialty-select" value={f.specialty} onChange={(e) => setF({ ...f, specialty: e.target.value })}>
              {Object.entries(LABOR_CATS).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])}</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("Cost orar (RON)", "Hourly cost (RON)")}><Input type="number" value={f.hourly_cost} onChange={(e) => setF({ ...f, hourly_cost: e.target.value })} /></Field>
          <Field label={tr("Telefon", "Phone")}><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Field label={tr("Bonus %", "Bonus %")}><Input type="number" value={f.bonus_pct} onChange={(e) => setF({ ...f, bonus_pct: e.target.value })} /></Field>
        </div>
        <DialogFooter><Button data-testid="mechanic-save-button" disabled={!f.name} onClick={save}>{tr("Salvează", "Save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Mechanics() {
  const { tr } = useLang();
  const { can } = useAuth();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [open, setOpen] = useState(false);
  const { data, reload } = useApi(`/mechanics?month=${month}`, [month]);
  const clock = async (id, action) => {
    try {
      await api.post(`/mechanics/${id}/clock`, { action });
      toast.success(action === "in" ? tr("Intrare pontată", "Clocked in") : tr("Ieșire pontată", "Clocked out"));
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div data-testid="mechanics-page">
      <PageHeader eyebrow={tr("Productivitate = ore facturate / ore prezente · Eficiență = ore normate / ore efective", "Productivity = billed / present h · Efficiency = norm / actual h")}
        title={tr("Mecanici & pontaj", "Mechanics & time")}
        actions={<>
          <Input type="month" data-testid="mechanics-month-input" className="w-44" value={month} onChange={(e) => setMonth(e.target.value)} />
          {can("settings") && <Button data-testid="add-mechanic-button" onClick={() => setOpen(true)}><Plus className="mr-1 h-4 w-4" />{tr("Angajat", "Technician")}</Button>}
        </>} />
      {!data ? <Loading /> : (
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="mechanics-table">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Angajat", "Technician")}</th><th className="px-2">{tr("Specializare", "Specialty")}</th><th className="px-2">Status</th>
                <th className="px-2 text-right">{tr("Ore prezente", "Present")}</th><th className="px-2 text-right">{tr("Ore lucrate", "Worked")}</th>
                <th className="px-2 text-right">{tr("Ore normate", "Norm")}</th><th className="px-2 text-right">{tr("Ore facturate", "Billed")}</th>
                <th className="px-2 text-right">{tr("Productivitate", "Productivity")}</th><th className="px-2 text-right">{tr("Eficiență", "Efficiency")}</th>
                <th className="px-2 text-right">Bonus</th><th className="px-2 text-right">{tr("Pontaj", "Clock")}</th>
              </tr></thead>
              <tbody>
                {data.map((m) => (
                  <tr key={m.id} className="h-11 border-b border-border/50" data-testid={`mechanic-row-${m.id}`}>
                    <td className="px-2 font-medium">{m.name}</td>
                    <td className="px-2 text-xs text-muted-foreground">{tr(...(LABOR_CATS[m.specialty] || ["", ""]))}</td>
                    <td className="px-2">
                      <span className={`inline-flex items-center gap-1.5 text-xs ${m.clocked_in ? "text-emerald-500" : "text-muted-foreground"}`}>
                        <span className={`h-2 w-2 rounded-full ${m.working_on ? "animate-pulse bg-orange-500" : m.clocked_in ? "bg-emerald-500" : "bg-slate-500"}`} />
                        {m.working_on ? tr("Lucrează", "Working") : m.clocked_in ? tr("Prezent", "Present") : tr("Absent", "Absent")}
                      </span>
                    </td>
                    <td className="px-2 text-right font-mono">{num(m.stats.attendance, 1)}</td><td className="px-2 text-right font-mono">{num(m.stats.worked, 1)}</td>
                    <td className="px-2 text-right font-mono">{num(m.stats.norm, 1)}</td><td className="px-2 text-right font-mono">{num(m.stats.billed, 1)}</td>
                    <td className={`px-2 text-right font-mono font-semibold ${pctCls(m.stats.productivity)}`}>{num(m.stats.productivity, 1)}%</td>
                    <td className={`px-2 text-right font-mono font-semibold ${pctCls(m.stats.efficiency)}`}>{num(m.stats.efficiency, 1)}%</td>
                    <td className="px-2 text-right font-mono text-xs">{m.bonus_pct || 0}%</td>
                    <td className="px-2 text-right">
                      {m.clocked_in ? (
                        <Button size="sm" variant="outline" data-testid={`clock-out-${m.id}`} onClick={() => clock(m.id, "out")}><LogOut className="mr-1 h-3 w-3" />{tr("Ieșire", "Out")}</Button>
                      ) : (
                        <Button size="sm" data-testid={`clock-in-${m.id}`} onClick={() => clock(m.id, "in")}><LogIn className="mr-1 h-3 w-3" />{tr("Intrare", "In")}</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <MechanicDialog open={open} onOpenChange={setOpen} onSaved={reload} />
    </div>
  );
}
