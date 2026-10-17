import { Link } from "react-router-dom";
import { Car, Clock, CheckCircle2, FileText, Wallet, TrendingUp, Gauge, Warehouse, Timer, Percent, AlertTriangle, Landmark } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar, Cell } from "recharts";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date } from "@/lib/format";
import { Kpi, Panel, PageHeader, Loading, STATUS, StatusBadge } from "@/components/common";

const STATUS_COLORS = { noua: "#3b82f6", diagnosticare: "#a855f7", asteapta_oferta: "#eab308", aprobata: "#10b981", in_lucru: "#f97316",
  asteapta_piese: "#f43f5e", finalizata: "#14b8a6", facturata: "#06b6d4", inchisa: "#64748b" };
const tip = { contentStyle: { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 4, fontSize: 12 } };

function Expirations() {
  const { tr } = useLang();
  const { data } = useApi("/expirations?days=30");
  const label = { itp_expiry: "ITP", rca_expiry: "RCA", casco_expiry: "CASCO", rovinieta_expiry: tr("Rovinietă", "Vignette") };
  return (
    <Panel title={tr("Expirări 30 zile", "Expiring in 30 days")} testid="dashboard-expirations">
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {(data || []).map((e, i) => (
          <div key={i} className="flex items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-accent">
            <span className="font-mono text-xs">{e.plate}</span>
            <span className="truncate px-2 text-muted-foreground">{e.client_name}</span>
            <span className={`font-mono text-xs ${e.date < new Date().toISOString().slice(0, 10) ? "text-rose-500" : "text-yellow-500"}`}>{label[e.kind]} · {date(e.date)}</span>
          </div>
        ))}
        {data && !data.length && <div className="text-sm text-muted-foreground">{tr("Nicio expirare.", "Nothing expiring.")}</div>}
      </div>
    </Panel>
  );
}

export default function Dashboard() {
  const { tr } = useLang();
  const { data: d } = useApi("/dashboard");
  const { data: wos } = useApi("/work-orders?active=true");
  if (!d) return <Loading />;
  const statusData = Object.keys(STATUS).map((k) => ({ k, name: tr(STATUS[k][0], STATUS[k][1]), v: d.by_status[k] || 0 }));
  return (
    <div data-testid="dashboard-page">
      <PageHeader eyebrow={tr("Dashboard executiv · timp real", "Executive dashboard · real time")} title={tr("Centrul de comandă", "Command center")} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi testid="kpi-in-service" label={tr("În service", "In service")} value={d.in_service} icon={Car} sub={`${d.in_progress} ${tr("în lucru", "in progress")}`} />
        <Kpi testid="kpi-waiting" label={tr("În așteptare", "Waiting")} value={d.waiting} icon={Clock} accent="text-yellow-500" />
        <Kpi testid="kpi-finished" label={tr("Finalizate", "Completed")} value={d.finished} icon={CheckCircle2} accent="text-emerald-500" sub={tr("de facturat", "to invoice")} />
        <Kpi testid="kpi-invoices" label={tr("Facturi luna", "Invoices month")} value={d.invoices_month.count} icon={FileText} accent="text-cyan-500" sub={money(d.invoices_month.gross)} />
        <Kpi testid="kpi-collected" label={tr("Încasări luna", "Collected month")} value={money(d.collected_month)} icon={Wallet} accent="text-emerald-500" />
        <Kpi testid="kpi-profit" label={tr("Profit brut luna", "Gross profit month")} value={money(d.profit_month)} icon={TrendingUp} sub={`${tr("Venit net", "Net revenue")} ${money(d.revenue_month)}`} />
        <Kpi testid="kpi-productivity" label={tr("Productivitate mecanici", "Mechanic productivity")} value={`${num(d.mechanic_productivity, 1)}%`} icon={Gauge} accent="text-cyan-500" sub={tr("ore facturate / ore prezente", "billed / present hours")} />
        <Kpi testid="kpi-elevators" label={tr("Ocupare elevatoare", "Lift occupancy")} value={`${d.elevator_occupancy.busy}/${d.elevator_occupancy.total}`} icon={Warehouse}
          sub={`${d.elevator_occupancy.total ? Math.round((d.elevator_occupancy.busy / d.elevator_occupancy.total) * 100) : 0}%`} />
        <Kpi testid="kpi-repair-time" label={tr("Timp mediu reparație", "Avg repair time")} value={`${num(d.avg_repair_hours, 1)} h`} icon={Timer} accent="text-purple-500" sub={tr("ultimele 90 zile", "last 90 days")} />
        <Kpi testid="kpi-parts-margin" label={tr("Marjă piese", "Parts margin")} value={`${num(d.parts_margin, 1)}%`} icon={Percent} accent="text-emerald-500" />
        <Kpi testid="kpi-receivables" label={tr("Creanțe clienți", "Receivables")} value={money(d.receivables)} icon={Landmark} accent="text-rose-500" />
        <Kpi testid="kpi-low-stock" label={tr("Stoc sub minim", "Low stock")} value={d.low_stock} icon={AlertTriangle} accent="text-yellow-500" sub={tr("articole", "items")} />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <Panel title={tr("Venituri vs. profit (6 luni)", "Revenue vs. profit (6 months)")} className="xl:col-span-2" testid="dashboard-revenue-chart">
          <div className="h-72">
            <ResponsiveContainer>
              <AreaChart data={d.series}>
                <defs>
                  <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#E05600" stopOpacity={0.4} /><stop offset="100%" stopColor="#E05600" stopOpacity={0} /></linearGradient>
                  <linearGradient id="gPro" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#00BCD4" stopOpacity={0.35} /><stop offset="100%" stopColor="#00BCD4" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={60} />
                <Tooltip {...tip} formatter={(v) => money(v)} />
                <Area type="monotone" dataKey="revenue" name={tr("Venit net", "Net revenue")} stroke="#E05600" fill="url(#gRev)" strokeWidth={2} />
                <Area type="monotone" dataKey="profit" name={tr("Profit brut", "Gross profit")} stroke="#00BCD4" fill="url(#gPro)" strokeWidth={2} />
                <Area type="monotone" dataKey="collected" name={tr("Încasări", "Collected")} stroke="#10b981" fill="none" strokeWidth={1.5} strokeDasharray="4 3" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title={tr("Comenzi pe status", "Orders by status")} testid="dashboard-status-chart">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={statusData} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={110} />
                <Tooltip {...tip} />
                <Bar dataKey="v" name="#" radius={[0, 3, 3, 0]}>{statusData.map((s) => <Cell key={s.k} fill={STATUS_COLORS[s.k]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel title={tr("Productivitate mecanici (luna curentă)", "Mechanic productivity (this month)")} className="xl:col-span-2" testid="dashboard-mechanics">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="py-2">{tr("Mecanic", "Mechanic")}</th><th className="text-right">{tr("Ore prezente", "Present h")}</th><th className="text-right">{tr("Ore lucrate", "Worked h")}</th>
                <th className="text-right">{tr("Ore facturate", "Billed h")}</th><th className="text-right">{tr("Productivitate", "Productivity")}</th><th className="text-right">{tr("Eficiență", "Efficiency")}</th>
              </tr></thead>
              <tbody>
                {d.mechanics.map((m) => (
                  <tr key={m.name} className="border-b border-border/50">
                    <td className="py-2 font-medium">{m.name}</td>
                    <td className="text-right font-mono">{num(m.attendance, 1)}</td><td className="text-right font-mono">{num(m.worked, 1)}</td>
                    <td className="text-right font-mono">{num(m.billed, 1)}</td>
                    <td className="text-right"><span className={`font-mono font-semibold ${m.productivity >= 80 ? "text-emerald-500" : m.productivity >= 50 ? "text-yellow-500" : "text-rose-500"}`}>{num(m.productivity, 1)}%</span></td>
                    <td className="text-right font-mono">{num(m.efficiency, 1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Expirations />
      </div>

      <Panel title={tr("Comenzi active", "Active orders")} className="mt-4" testid="dashboard-active-orders">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {(wos || []).slice(0, 9).map((w) => (
            <Link key={w.id} to={`/work-orders/${w.id}`} className="flex items-center justify-between rounded border px-3 py-2 transition-colors hover:border-primary/60">
              <div className="min-w-0">
                <div className="font-mono text-xs text-primary">{w.number}</div>
                <div className="truncate text-sm font-medium">{w.vehicle.make} {w.vehicle.model} · <span className="font-mono">{w.vehicle.plate}</span></div>
              </div>
              <StatusBadge status={w.status} />
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
