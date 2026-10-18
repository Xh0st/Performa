import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ClipboardPlus, Wrench, Users, Car, HardHat, Boxes, FileText, Wallet, Sparkles, Settings, ShieldCheck,
  Menu, Sun, Moon, LogOut, Plus, FileCode2,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ROLE_LABELS } from "@/components/common";

const NAV = [
  { group: ["Operațional", "Operations"], items: [
    ["/", "dashboard", LayoutDashboard, "Dashboard", "Dashboard", "dashboard"],
    ["/reception", "reception", ClipboardPlus, "Recepție", "Reception", "reception"],
    ["/work-orders", "workorders", Wrench, "Comenzi de lucru", "Work orders", "work-orders"],
    ["/clients", "crm", Users, "Clienți CRM", "CRM Clients", "clients"],
    ["/vehicles", "vehicles", Car, "Parc auto", "Vehicles", "vehicles"],
    ["/mechanics", "mechanics", HardHat, "Mecanici & pontaj", "Mechanics & time", "mechanics"],
  ]},
  { group: ["Magazie", "Warehouse"], items: [["/stock", "stock", Boxes, "Stocuri & NIR", "Stock & GRN", "stock"]] },
  { group: ["Financiar", "Finance"], items: [
    ["/invoices", "invoices", FileText, "Facturi & e-Factura", "Invoices & e-Invoice", "invoices"],
    ["/cash", "payments", Wallet, "Încasări & casă", "Payments & cash", "cash"],
  ]},
  { group: ["Inteligență", "Intelligence"], items: [["/ai", "ai", Sparkles, "AI Advisor", "AI Advisor", "ai"]] },
  { group: ["Administrare", "Administration"], items: [
    ["/users", "users", ShieldCheck, "Utilizatori & audit", "Users & audit", "users"],
    ["/settings", "settings", Settings, "Setări companie", "Company settings", "settings"],
    ["/efactura", "settings", FileCode2, "eFactura / Setări API", "e-Invoice / API settings", "efactura"],
  ]},
];

function SideNav({ onNav }) {
  const { can } = useAuth();
  const { tr } = useLang();
  return (
    <nav className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-5">
      <div className="flex items-center gap-2 px-2">
        <div
          className="flex h-9 w-9 items-center justify-center rounded bg-primary font-heading text-lg font-extrabold text-primary-foreground"
          data-testid="app-brand-mark"
        >
          PA
        </div>
        <div>
          <div
            className="font-heading text-lg font-extrabold uppercase leading-none tracking-wide"
            data-testid="app-brand-name"
          >
            Performa Auto
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">ERP · RO</div>
        </div>
      </div>
      {NAV.map((g) => {
        const items = g.items.filter((i) => can(i[1]));
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
  const { user, logout, can } = useAuth();
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
          {can("reception") && (
            <Button size="sm" onClick={() => nav("/reception")} data-testid="header-new-reception-button" className="active:scale-95">
              <Plus className="mr-1 h-4 w-4" /> {tr("Recepție nouă", "New reception")}
            </Button>
          )}
          <Button variant="outline" size="sm" className="font-mono" data-testid="nav-language-toggle" onClick={() => setLang(lang === "ro" ? "en" : "ro")}>
            {lang === "ro" ? "RO" : "EN"}
          </Button>
          <Button variant="outline" size="icon" className="h-9 w-9" data-testid="nav-theme-toggle" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
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
