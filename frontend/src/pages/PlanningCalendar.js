import { useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarDays, Plus, RotateCcw, Trash2 } from "lucide-react";
import { Calendar, dateFnsLocalizer } from "react-big-calendar";
import withDragAndDrop from "react-big-calendar/lib/addons/dragAndDrop";
import { addDays, endOfWeek, format, getDay, parse, startOfDay, startOfMonth, startOfWeek } from "date-fns";
import { ro } from "date-fns/locale";
import "react-big-calendar/lib/css/react-big-calendar.css";
import "react-big-calendar/lib/addons/dragAndDrop/styles.css";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
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
import { Field, Loading, NativeSelect, PageHeader, Panel } from "@/components/common";

const DndCalendar = withDragAndDrop(Calendar);
const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales: { ro },
});
const STATUS = {
  programat: "Programat",
  sosit: "Sosit în service",
  in_lucru: "În lucru",
  finalizat: "Finalizat",
  neprezentat: "Neprezentat",
  anulat: "Anulat",
};
const EMPTY = {
  client_id: "",
  vehicle_id: "",
  starts_at: "",
  ends_at: "",
  elevator: "",
  mechanic_ids: [],
  advisor: "",
  title: "",
  notes: "",
};

function toLocal(value) {
  return value ? format(new Date(value), "yyyy-MM-dd'T'HH:mm") : "";
}

function rangeFor(date, view) {
  const base = new Date(date);
  if (view === "month") {
    const monthStart = startOfMonth(base);
    const visibleEnd = endOfWeek(
      new Date(base.getFullYear(), base.getMonth() + 1, 0),
      { weekStartsOn: 1 }
    );
    return [startOfWeek(monthStart, { weekStartsOn: 1 }), startOfDay(addDays(visibleEnd, 1))];
  }
  if (view === "day") {
    const dayStart = new Date(base.getFullYear(), base.getMonth(), base.getDate());
    return [dayStart, addDays(dayStart, 1)];
  }
  const weekStart = startOfWeek(base, { weekStartsOn: 1 });
  return [weekStart, addDays(weekStart, 7)];
}

export default function PlanningCalendar() {
  const { tr } = useLang();
  const [date, setDate] = useState(new Date());
  const [view, setView] = useState("week");
  const [bayMode, setBayMode] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [current, setCurrent] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState(false);
  const [start, end] = rangeFor(date, bayMode ? "day" : view);
  const query = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
  const { data: appointments, reload } = useApi(`/appointments?${query}`, [query]);
  const { data: capacity, reload: reloadCapacity } = useApi(`/appointments/capacity?${query}`, [query]);
  const { data: clients } = useApi("/clients");
  const { data: vehicles } = useApi(form.client_id ? `/vehicles?client_id=${form.client_id}` : null, [form.client_id]);
  const { data: mechanics } = useApi("/mechanics");

  const events = useMemo(() => (appointments || []).map((item) => ({
    ...item,
    title: `${item.title} · ${item.vehicle_label}`,
    start: new Date(item.starts_at),
    end: new Date(item.ends_at),
    resourceId: item.elevator,
  })), [appointments]);

  const openNew = (slot) => {
    setCurrent(null);
    setForm({
      ...EMPTY,
      starts_at: toLocal(slot?.start.toISOString() || new Date().toISOString()),
      ends_at: toLocal(slot?.end.toISOString() || new Date(Date.now() + 3600000).toISOString()),
    });
    setDialog(true);
  };
  const openEdit = (event) => {
    setCurrent(event);
    setForm({
      client_id: event.client_id,
      vehicle_id: event.vehicle_id,
      starts_at: toLocal(event.starts_at),
      ends_at: toLocal(event.ends_at),
      elevator: event.elevator,
      mechanic_ids: event.mechanic_ids || [],
      advisor: event.advisor || "",
      title: event.title.split(" · ")[0],
      notes: event.notes || "",
    });
    setDialog(true);
  };
  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        ...form,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
      };
      if (current) await api.put(`/appointments/${current.id}`, payload);
      else await api.post("/appointments", payload);
      toast.success(tr("Programare salvată", "Appointment saved"));
      setDialog(false);
      reload();
      reloadCapacity();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setBusy(false);
    }
  };
  const move = async ({ event, start: nextStart, end: nextEnd }) => {
    try {
      await api.put(`/appointments/${event.id}`, {
        ...formFromEvent(event),
        starts_at: nextStart.toISOString(),
        ends_at: nextEnd.toISOString(),
      });
      reload();
      reloadCapacity();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };
  const updateStatus = async (status) => {
    if (!current) return;
    try {
      const response = await api.post(`/appointments/${current.id}/status`, { status });
      setCurrent(response.data);
      toast.success(status === "in_lucru" ? tr("Comandă de lucru creată", "Work order created") : tr("Status actualizat", "Status updated"));
      reload();
      reloadCapacity();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };
  const remove = async () => {
    if (!current) return;
    setBusy(true);
    try {
      await api.delete(`/appointments/${current.id}`);
      toast.success(tr("Programare ștearsă", "Appointment deleted"));
      setDeleteDialog(false);
      setDialog(false);
      setCurrent(null);
      reload();
      reloadCapacity();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setBusy(false);
    }
  };
  if (!appointments || !capacity) return <Loading />;

  return (
    <div data-testid="planning-calendar-page">
      <PageHeader
        eyebrow={tr("Programări · capacitate atelier · resurse", "Appointments · workshop capacity · resources")}
        title={tr("Planificare calendar", "Planning calendar")}
        actions={(
          <Button data-testid="planning-new-button" onClick={() => openNew()}>
            <Plus className="mr-1 h-4 w-4" />
            {tr("Programare", "Appointment")}
          </Button>
        )}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {["day", "week", "month"].map((item) => (
          <Button key={item} variant={!bayMode && view === item ? "default" : "outline"} size="sm" data-testid={`planning-view-${item}`} onClick={() => { setBayMode(false); setView(item); }}>
            {tr({ day: "Zi", week: "Săptămână", month: "Lună" }[item], item)}
          </Button>
        ))}
        <Button variant={bayMode ? "default" : "outline"} size="sm" data-testid="planning-view-bays" onClick={() => setBayMode(true)}>
          {tr("Rampe / elevatoare", "Bays / lifts")}
        </Button>
        <div className="ml-auto font-mono text-xs" data-testid="planning-capacity">
          {tr("Ocupare", "Occupancy")}: {capacity.occupancy}% · {capacity.count} {tr("programări", "appointments")}
        </div>
      </div>
      <Panel className="min-w-0" testid="planning-calendar-panel">
        <div className="min-w-0 overflow-x-auto" data-testid="planning-calendar">
          <DndCalendar
            localizer={localizer}
            events={events}
            date={date}
            view={bayMode ? "day" : view}
            onNavigate={setDate}
            onView={(nextView) => { setBayMode(false); setView(nextView); }}
            views={bayMode ? ["day"] : ["day", "week", "month"]}
            resources={bayMode ? capacity.elevators.map((name) => ({ id: name, title: name })) : undefined}
            resourceIdAccessor="id"
            resourceTitleAccessor="title"
            resourceAccessor="resourceId"
            selectable
            resizable
            popup
            culture="ro"
            messages={{
              today: "Astăzi",
              previous: "Înapoi",
              next: "Înainte",
              day: "Zi",
              week: "Săptămână",
              month: "Lună",
            }}
            scrollToTime={new Date(1970, 0, 1, 8)}
            startAccessor="start"
            endAccessor="end"
            onSelectSlot={openNew}
            onSelectEvent={openEdit}
            onEventDrop={move}
            onEventResize={move}
            draggableAccessor={(event) => !["finalizat", "anulat"].includes(event.status)}
            style={{ height: 640, minWidth: bayMode ? 760 : 620 }}
          />
        </div>
      </Panel>
      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent className="max-w-2xl" data-testid="planning-dialog">
          <DialogHeader><DialogTitle>{current ? tr("Editează programarea", "Edit appointment") : tr("Programare nouă", "New appointment")}</DialogTitle></DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={tr("Client", "Client")}><NativeSelect data-testid="planning-client-select" value={form.client_id} onChange={(event) => setForm({ ...form, client_id: event.target.value, vehicle_id: "" })}><option value="">—</option>{(clients || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Field>
            <Field label={tr("Vehicul", "Vehicle")}><NativeSelect data-testid="planning-vehicle-select" value={form.vehicle_id} disabled={!form.client_id} onChange={(event) => setForm({ ...form, vehicle_id: event.target.value })}><option value="">—</option>{(vehicles || []).map((item) => <option key={item.id} value={item.id}>{item.plate} · {item.make} {item.model}</option>)}</NativeSelect></Field>
            <Field label={tr("Începe", "Starts")}><Input data-testid="planning-start-input" type="datetime-local" value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></Field>
            <Field label={tr("Se termină", "Ends")}><Input data-testid="planning-end-input" type="datetime-local" value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></Field>
            <Field label={tr("Rampă / elevator", "Bay / lift")}><NativeSelect data-testid="planning-elevator-select" value={form.elevator} onChange={(event) => setForm({ ...form, elevator: event.target.value })}><option value="">—</option>{capacity.elevators.map((item) => <option key={item}>{item}</option>)}</NativeSelect></Field>
            <Field label={tr("Consilier service", "Service advisor")}><Input data-testid="planning-advisor-input" value={form.advisor} onChange={(event) => setForm({ ...form, advisor: event.target.value })} /></Field>
            <Field label={tr("Mecanici alocați", "Assigned mechanics")} className="sm:col-span-2"><div className="flex flex-wrap gap-3">{(mechanics || []).map((mechanic) => <label key={mechanic.id} className="flex items-center gap-2 text-sm"><Checkbox data-testid={`planning-mechanic-${mechanic.id}`} checked={form.mechanic_ids.includes(mechanic.id)} onCheckedChange={(checked) => setForm({ ...form, mechanic_ids: checked ? [...form.mechanic_ids, mechanic.id] : form.mechanic_ids.filter((id) => id !== mechanic.id) })} />{mechanic.name}</label>)}</div></Field>
            <Field label={tr("Titlu intervenție", "Service title")} className="sm:col-span-2"><Input data-testid="planning-title-input" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></Field>
            <Field label={tr("Observații", "Notes")} className="sm:col-span-2"><Textarea data-testid="planning-notes-input" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field>
          </div>
          {current && <div className="mt-3 flex flex-wrap gap-2"><NativeSelect data-testid="planning-status-select" value={current.status} onChange={(event) => updateStatus(event.target.value)}>{Object.entries(STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</NativeSelect>{current.work_order_id && <Button variant="outline" data-testid="planning-open-work-order-button" onClick={() => window.open(`/work-orders/${current.work_order_id}`, "_blank")}><CalendarDays className="mr-1 h-4 w-4" />{tr("Comandă", "Work order")}</Button>}</div>}
          <DialogFooter className="gap-2 sm:space-x-0">
            {current && <Button variant="destructive" data-testid="planning-delete-button" disabled={busy} onClick={() => setDeleteDialog(true)}><Trash2 className="h-4 w-4" />{tr("Șterge", "Delete")}</Button>}
            <Button data-testid="planning-save-button" disabled={busy || !form.client_id || !form.vehicle_id || !form.title || !form.starts_at || !form.ends_at} onClick={save}>{busy ? <RotateCcw className="h-4 w-4 animate-spin" /> : tr("Salvează", "Save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog open={deleteDialog} onOpenChange={setDeleteDialog}>
        <AlertDialogContent data-testid="planning-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{tr("Șterge programarea?", "Delete appointment?")}</AlertDialogTitle>
            <AlertDialogDescription>{current?.work_order_id ? tr("Programarea și notificările asociate vor fi eliminate. Comanda de lucru deja creată rămâne intactă.", "The appointment and notifications will be removed. The existing work order remains intact.") : tr("Programarea și notificările asociate vor fi eliminate definitiv.", "The appointment and its associated notifications will be permanently removed.")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:space-x-0">
            <AlertDialogCancel data-testid="planning-delete-cancel-button">{tr("Renunță", "Cancel")}</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" data-testid="planning-delete-confirm-button" disabled={busy} onClick={remove}>{tr("Șterge definitiv", "Delete permanently")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function formFromEvent(event) {
  return {
    client_id: event.client_id,
    vehicle_id: event.vehicle_id,
    starts_at: event.starts_at,
    ends_at: event.ends_at,
    elevator: event.elevator,
    mechanic_ids: event.mechanic_ids || [],
    advisor: event.advisor || "",
    title: event.title.split(" · ")[0],
    notes: event.notes || "",
  };
}