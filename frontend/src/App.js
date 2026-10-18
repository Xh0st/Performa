import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { PrefsProvider, useLang } from "@/lib/prefs";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import { Loading } from "@/components/common";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import Vehicles from "@/pages/Vehicles";
import Reception from "@/pages/Reception";
import WorkOrders from "@/pages/WorkOrders";
import WorkOrderDetail from "@/pages/WorkOrderDetail";
import Mechanics from "@/pages/Mechanics";
import Stock from "@/pages/Stock";
import Invoices from "@/pages/Invoices";
import InvoiceDetail from "@/pages/InvoiceDetail";
import Cash from "@/pages/Cash";
import AiAssistant from "@/pages/AiAssistant";
import Users from "@/pages/Users";
import SettingsPage from "@/pages/Settings";
import EfacturaSettings from "@/pages/EfacturaSettings";
import RarAutopassSettings from "@/pages/RarAutopassSettings";
import PlanningCalendar from "@/pages/PlanningCalendar";
import FinalInspectionReport from "@/pages/FinalInspectionReport";
import PublicQuote from "@/pages/PublicQuote";
import PrintDoc from "@/pages/PrintDoc";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Guard({ module, children }) {
  const { can, user } = useAuth();
  const { tr } = useLang();
  if (!can(module)) {
    if (module === "dashboard") {
      const first = user.permissions?.[0];
      const map = { workorders: "/work-orders", mechanics: "/mechanics", stock: "/stock", invoices: "/invoices", payments: "/cash", crm: "/clients", vehicles: "/vehicles" };
      if (first && map[first]) return <Navigate to={map[first]} replace />;
    }
    return <div data-testid="access-denied" className="py-20 text-center text-muted-foreground">{tr("Nu aveți acces la acest modul.", "You do not have access to this module.")}</div>;
  }
  return children;
}

const g = (m, el) => <Guard module={m}>{el}</Guard>;

function App() {
  return (
    <PrefsProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/approve/:token" element={<PublicQuote />} />
            <Route path="/print/:kind/:id" element={<Protected><PrintDoc /></Protected>} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route path="/" element={g("dashboard", <Dashboard />)} />
              <Route path="/clients" element={g("crm", <Clients />)} />
              <Route path="/clients/:id" element={g("crm", <ClientDetail />)} />
              <Route path="/vehicles" element={g("vehicles", <Vehicles />)} />
              <Route path="/reception" element={g("reception", <Reception />)} />
              <Route path="/work-orders" element={g("workorders", <WorkOrders />)} />
              <Route path="/work-orders/:id" element={g("workorders", <WorkOrderDetail />)} />
              <Route path="/mechanics" element={g("mechanics", <Mechanics />)} />
              <Route path="/stock" element={g("stock", <Stock />)} />
              <Route path="/invoices" element={g("invoices", <Invoices />)} />
              <Route path="/invoices/:id" element={g("invoices", <InvoiceDetail />)} />
              <Route path="/cash" element={g("payments", <Cash />)} />
              <Route path="/ai" element={g("ai", <AiAssistant />)} />
              <Route path="/users" element={g("users", <Users />)} />
              <Route path="/settings" element={g("settings", <SettingsPage />)} />
              <Route path="/efactura" element={g("settings", <EfacturaSettings />)} />
              <Route path="/rar-autopass" element={g("settings", <RarAutopassSettings />)} />
              <Route path="/planning" element={g("planning", <PlanningCalendar />)} />
              <Route path="/reports/final-inspections" element={g("reports", <FinalInspectionReport />)} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster richColors position="top-right" />
      </AuthProvider>
    </PrefsProvider>
  );
}

export default App;
