import { forwardRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ClipboardPlus, Wrench, Users, Car, HardHat, Boxes, FileText, Wallet, Sparkles, Settings, ShieldCheck,
  Building2, Menu, Sun, Moon, LogOut, Plus, FileCode2, ClipboardCheck, CalendarDays, BookOpenCheck, ShieldPlus, ListChecks,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLang } from "@/lib/prefs";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
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

// Radix Slot (TooltipTrigger asChild) stringifies function classNames; keep NavLink's function className internal.
const SideLink = forwardRef(({ classFn, className: slotClassName, ...props }, ref) => (
  <NavLink ref={ref} {...props} className={(state) => `${classFn(state)} ${slotClassName || ""}`} />
));
SideLink.displayName = "SideLink";

function SideNav({ onNav, collapsed = false }) {
  const { can, user } = useAuth();
  const { tr } = useLang();
  return (
    <TooltipProvider delayDuration={180}>
      <nav className={`sidebar-scroll flex h-full flex-col overflow-y-auto py-5 ${collapsed ? "gap-3 px-2" : "gap-5 px-3"}`}>
      <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "justify-between gap-2 px-2"}`}>
        <NavLink
          to="/"
          end
          onClick={onNav}
          data-testid="sidebar-brand-dashboard-link"
          aria-label={tr("Dashboard", "Dashboard")}
          title={tr("Dashboard", "Dashboard")}
          className={`flex items-center rounded outline-none transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring ${collapsed ? "justify-center" : "gap-2"}`}
        >
        <img
          src="/performa-logo-dark.png"
          alt="Performa Auto"
          className={`shrink-0 object-contain ${collapsed ? "h-9 w-9" : "h-10 w-16"}`}
          data-testid="app-brand-mark"
        />
        {!collapsed && <div>
          <div
            className="font-heading text-base font-extrabold uppercase leading-none tracking-wide"
            data-testid="app-brand-name"
          >
            Performa Auto
          </div>
        </div>}
        </NavLink>
      </div>
      {NAV.map((g) => {
        const items = g.items.filter((i) => can(i[1]) && (!i[6] || user?.platform_role === "SUPERADMIN"));
        if (!items.length) return null;
        return (
          <div key={g.group[0]}>
            {!collapsed && <div className="eyebrow mb-2 px-2">{tr(g.group[0], g.group[1])}</div>}
            {items.map(([to, , Icon, ro, en, tid]) => {
              const link = <SideLink key={to} to={to} end={to === "/"} onClick={onNav} data-testid={`sidebar-${tid}-link`}
                aria-label={tr(ro, en)}
                classFn={({ isActive }) =>
                  `mb-0.5 flex rounded text-sm font-medium transition-colors duration-150 ${collapsed ? "h-11 w-11 items-center justify-center" : "items-center gap-3 px-2 py-2"} ${
                    isActive ? "bg-primary/10 text-primary shadow-[inset_2px_0_0_hsl(var(--primary))]" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}>
                <Icon className="h-5 w-5 shrink-0" /> {!collapsed && tr(ro, en)}
              </SideLink>;
              if (!collapsed) return link;
              return <Tooltip key={to}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right" data-testid={`sidebar-${tid}-tooltip`}>
                  <div className="space-y-0.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider opacity-70">{tr(g.group[0], g.group[1])}</div>
                    <div className="font-semibold">{tr(ro, en)}</div>
                  </div>
                </TooltipContent>
              </Tooltip>;
            })}
          </div>
        );
      })}
      </nav>
    </TooltipProvider>
  );
}

export default function Layout() {
  const { user, logout, switchBranch, can } = useAuth();
  const { lang, setLang, theme, setTheme, tr } = useLang();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar-collapsed") !== "false");
  const nav = useNavigate();
  const toggleSidebar = () => setCollapsed((current) => {
    const next = !current;
    localStorage.setItem("sidebar-collapsed", String(next));
    return next;
  });
  return (
    <div className="flex min-h-screen">
      <aside className={`sticky top-0 hidden h-screen shrink-0 border-r bg-card transition-[width] duration-200 lg:block ${collapsed ? "w-16" : "w-60"}`}>
        <SideNav collapsed={collapsed} />
      </aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="sr-only">{tr("Navigare principală", "Main navigation")}</SheetTitle>
          <SideNav onNav={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur-xl sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} data-testid="mobile-menu-button"><Menu className="h-5 w-5" /></Button>
          <Button
            variant="ghost"
            size="icon"
            className="hidden h-9 w-9 lg:inline-flex"
            data-testid="sidebar-collapse-toggle"
            aria-label={collapsed ? tr("Extinde meniul", "Expand menu") : tr("Restrânge meniul", "Collapse menu")}
            title={collapsed ? tr("Extinde meniul", "Expand menu") : tr("Restrânge meniul", "Collapse menu")}
            onClick={toggleSidebar}
          >
            {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
          </Button>
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
