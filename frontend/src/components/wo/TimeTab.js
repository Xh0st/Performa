import { toast } from "sonner";
import { Play, Square } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { LABOR_CATS, Empty } from "@/components/common";

const hours = (e) => ((e.end ? new Date(e.end) : new Date()) - new Date(e.start)) / 36e5;

export default function TimeTab({ wo, onChange }) {
  const { tr } = useLang();
  const { data: mechanics, reload } = useApi("/mechanics");
  const names = Object.fromEntries((mechanics || []).map((m) => [m.id, m.name]));
  const act = async (mid, action) => {
    try {
      onChange((await api.post(`/work-orders/${wo.id}/timer`, { mechanic_id: mid, action })).data);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const total = wo.time_entries.reduce((s, e) => s + hours(e), 0);
  const norm = wo.lines.filter((l) => l.type === "labor").reduce((s, l) => s + l.qty, 0);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-2">
        <div className="eyebrow">{tr("Pontaj automat pe lucrare", "Automatic job time tracking")}</div>
        {(mechanics || []).map((m) => {
          const here = m.working_on === wo.id;
          return (
            <div key={m.id} className="flex items-center justify-between rounded border px-3 py-2">
              <div><div className="text-sm font-medium">{m.name}</div><div className="text-[11px] text-muted-foreground">{tr(...(LABOR_CATS[m.specialty] || ["", ""]))}{m.working_on && !here ? ` · ${tr("ocupat altă lucrare", "busy on another job")}` : ""}</div></div>
              {here ? (
                <Button size="sm" variant="destructive" data-testid={`timer-stop-${m.id}`} onClick={() => act(m.id, "stop")}><Square className="mr-1 h-3 w-3" />Stop</Button>
              ) : (
                <Button size="sm" variant="outline" data-testid={`timer-start-${m.id}`} onClick={() => act(m.id, "start")}><Play className="mr-1 h-3 w-3" />Start</Button>
              )}
            </div>
          );
        })}
      </div>
      <div>
        <div className="mb-3 grid grid-cols-3 gap-2 text-center">
          <div className="rounded border p-2"><div className="eyebrow">{tr("Ore efective", "Actual h")}</div><div className="font-mono text-lg">{num(total, 2)}</div></div>
          <div className="rounded border p-2"><div className="eyebrow">{tr("Ore normate", "Norm h")}</div><div className="font-mono text-lg">{num(norm, 2)}</div></div>
          <div className="rounded border p-2"><div className="eyebrow">{tr("Eficiență", "Efficiency")}</div><div className="font-mono text-lg text-primary">{total ? num((norm / total) * 100, 0) : 0}%</div></div>
        </div>
        {!wo.time_entries.length ? <Empty text={tr("Nicio înregistrare.", "No entries.")} /> : (
          <table className="w-full text-sm"><tbody>
            {wo.time_entries.map((e) => (
              <tr key={e.id} className="h-9 border-b border-border/50">
                <td>{names[e.mechanic_id]}</td><td className="font-mono text-xs">{dt(e.start)}</td><td className="font-mono text-xs">{e.end ? dt(e.end) : <span className="text-emerald-500">{tr("în curs", "running")}</span>}</td>
                <td className="text-right font-mono">{num(hours(e), 2)} h</td>
              </tr>
            ))}
          </tbody></table>
        )}
      </div>
    </div>
  );
}
