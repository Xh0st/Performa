import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ClipboardPlus, Wrench, Users, Car, HardHat, Boxes, FileText, Wallet, Sparkles, Settings, ShieldCheck,
  Building2, Menu, Sun, Moon, LogOut, Plus, FileCode2, ClipboardCheck, CalendarDays, BookOpenCheck, ShieldPlus, ListChecks,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLang } from "@/lib/prefs";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ROLE_LABELS } from "@/components/common";
import { toast } from "sonner";

const NAV = [
  { group: ["Operațional", "Operations"], items: [
    ["/", "dashboard", LayoutDashboard, "Dashboard", "Dashboard", "dashboard"],
    ["/reception", "reception", ClipboardPlus, "Recepție", "Reception", "reception"],
    ["/work-orders", "workorders", Wrench, "Comenzi de lucru", "Work orders", "work-orders"],
    ["/clients", "crm", Users, "Clienți", "Clients", "clients"],
    ["/vehicles", "vehicles", Car, "Vehicule", "Vehicles", "vehicles"],
    ["/mechanics", "mechanics", HardHat, "Mecanici & pontaj", "Mechanics & time", "mechanics"],
    ["/planning", "planning", CalendarDays, "Planificare calendar", "Planning calendar", "planning"],
  ]},
  { group: ["Magazie", "Warehouse"], items: [["/stock", "stock", Boxes, "Stocuri & NIR", "Stock & GRN", "stock"]] },
  { group: ["Financiar", "Finance"], items: [
    ["/invoices", "invoices", FileText, "Facturi & e-Factura", "Invoices & e-Invoice", "invoices"],
    ["/cash", "payments", Wallet, "Încasări & casă", "Payments & cash", "cash"],
    ["/warranties", "warranties", ShieldPlus, "Garanții & reclamații", "Warranties & claims", "warranties"],
  ]},
  { group: ["Inteligență", "Intelligence"], items: [["/ai", "ai", Sparkles, "AI Advisor", "AI Advisor", "ai"]] },
  { group: ["Rapoarte", "Reports"], items: [["/reports/final-inspections", "reports", BookOpenCheck, "Registru Inspecții Finale", "Final Inspections Register", "final-inspections"]] },
  { group: ["Administrare", "Administration"], items: [
    ["/users", "users", ShieldCheck, "Utilizatori & audit", "Users & audit", "users"],
    ["/settings", "settings", Settings, "Setări companie", "Company settings", "settings"],
    ["/efactura", "settings", FileCode2, "eFactura / Setări API", "e-Invoice / API settings", "efactura"],
    ["/rar-autopass", "settings", ClipboardCheck, "RAR AutoPass", "RAR AutoPass", "rar-autopass"],
    ["/closure-review", "settings", ListChecks, "Verificare închideri", "Closure review", "closure-review"],
    ["/platform/tenants", "settings", Building2, "Tenants & licențe", "Tenants & licenses", "platform-tenants", true],
  ]},
];

function SideNav({ onNav }) {
  const { can, user } = useAuth();
  const { tr } = useLang();
  return (
    <nav className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-5">
      <div className="flex items-center gap-2 px-2">
        <img
          src="/performa-logo.png"
          alt="Performa Auto"
          className="h-10 w-10 shrink-0 object-contain"
          data-testid="app-brand-mark"
        />
        <div>
          <div
            className="font-heading text-base font-extrabold uppercase leading-none tracking-wide"
            data-testid="app-brand-name"
          >
            Performa Auto
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">ERP · RO</div>
        </div>
      </div>
      {NAV.map((g) => {
        const items = g.items.filter((i) => can(i[1]) && (!i[6] || user?.platform_role === "SUPERADMIN"));
        if (!items.length) return null;
        return (
          <div key={g.group[0]}>
            <div className="eyebrow mb-2 px-2">{tr(g.group[0], g.group[1])}</div>
            {items.map(([to, , Icon, ro, en, tid]) => (
              <NavLink key={to} to={to} end={to === "/"} onClick={onNav} data-testid={`sidebar-${tid}-link`}
                className={({ isActive }) =>
                  `mb-0.5 flex items-center gap-3 rounded px-2 py-2 text-sm font-medium transition-colors duration-150 ${
                    isActive ? "bg-primary/10 text-primary shadow-[inset_2px_0_0_hsl(var(--primary))]" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}>
                <Icon className="h-4 w-4" /> {tr(ro, en)}
              </NavLink>
            ))}
          </div>
        );
      })}
    </nav>
  );
}

export default function Layout() {
  const { user, logout, switchBranch, can } = useAuth();
  const { lang, setLang, theme, setTheme, tr } = useLang();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r bg-card lg:block">
        <SideNav />
      </aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SideNav onNav={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur-xl sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} data-testid="mobile-menu-button"><Menu className="h-5 w-5" /></Button>
          <div className="hidden font-mono text-xs uppercase tracking-widest text-muted-foreground md:block">{new Date().toLocaleDateString(lang === "ro" ? "ro-RO" : "en-GB", { weekday: "long", day: "numeric", month: "long" })}</div>
          <div className="flex-1" />
          {user?.branches?.length > 1 && (
            <select
              className="h-9 w-20 min-w-0 rounded border bg-background px-2 text-sm sm:w-auto sm:max-w-48"
              data-testid="active-branch-selector"
              value={user.active_branch_id}
              onChange={(event) => switchBranch(event.target.value).catch((error) => toast.error(errMsg(error)))}
            >
              {user.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
            </select>
          )}
          {can("reception") && (
            <Button
              size="sm"
              onClick={() => nav("/reception")}
              data-testid="header-new-reception-button"
              className="h-9 w-9 p-0 active:scale-95 sm:w-auto sm:px-3"
              aria-label={tr("Recepție nouă", "New reception")}
              title={tr("Recepție nouă", "New reception")}
            >
              <Plus className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">{tr("Recepție nouă", "New reception")}</span>
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="h-9 w-9 p-0 font-mono sm:w-auto sm:px-3"
            data-testid="nav-language-toggle"
            onClick={() => setLang(lang === "ro" ? "en" : "ro")}
            aria-label={tr("Schimbă limba", "Change language")}
            title={tr("Schimbă limba", "Change language")}
          >
            {lang === "ro" ? "RO" : "EN"}
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9"
            data-testid="nav-theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={theme === "dark" ? tr("Activează tema luminoasă", "Use light theme") : tr("Activează tema întunecată", "Use dark theme")}
            title={theme === "dark" ? tr("Activează tema luminoasă", "Use light theme") : tr("Activează tema întunecată", "Use dark theme")}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <div className="hidden text-right sm:block">
            <div data-testid="header-user-name" className="text-sm font-semibold leading-tight">{user?.name}</div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{tr(...(ROLE_LABELS[user?.role] || ["", ""]))}</div>
          </div>
          <Button variant="ghost" size="icon" data-testid="logout-button" onClick={async () => { await logout(); nav("/login"); }}>
            <LogOut className="h-4 w-4" />
          </Button>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
