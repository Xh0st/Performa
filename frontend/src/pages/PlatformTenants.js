import { useState } from "react";
import { Building2, Plus, Save } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, useApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, Loading, NativeSelect, PageHeader, Panel } from "@/components/common";

const EMPTY_TENANT = { tenant_id: "", company_name: "", cui: "", reg_com: "", subscription_plan: "BASIC", max_branches_allowed: 1 };
const EMPTY_BRANCH = { branch_id: "", branch_name: "", address: "", rar_authorization_code: "", is_main_branch: false };

export default function PlatformTenants() {
  const { user } = useAuth();
  const { data: tenants, reload } = useApi(user?.platform_role === "SUPERADMIN" ? "/platform/tenants" : null, [user?.platform_role]);
  const [tenant, setTenant] = useState(EMPTY_TENANT);
  const [branch, setBranch] = useState(EMPTY_BRANCH);
  const [selected, setSelected] = useState("");
  if (!user || user.platform_role !== "SUPERADMIN") return <div className="p-8" data-testid="platform-access-denied">Acces rezervat Superadmin.</div>;
  if (!tenants) return <Loading />;
  const createTenant = async () => {
    try {
      await api.post("/platform/tenants", { ...tenant, max_branches_allowed: Number(tenant.max_branches_allowed) });
      toast.success("Tenant creat");
      setTenant(EMPTY_TENANT);
      reload();
    } catch (error) { toast.error(errMsg(error)); }
  };
  const createBranch = async () => {
    try {
      await api.post(`/platform/tenants/${selected}/branches`, branch);
      toast.success("Punct de lucru creat");
      setBranch(EMPTY_BRANCH);
      reload();
    } catch (error) { toast.error(errMsg(error)); }
  };
  return <div data-testid="platform-tenants-page"><PageHeader eyebrow="Platformă · licențe · izolare" title="Superadmin · Tenants" /><div className="grid gap-4 xl:grid-cols-2"><Panel title="Tenant nou" testid="create-tenant-panel"><div className="grid gap-3 sm:grid-cols-2"><Field label="ID tenant"><Input data-testid="tenant-id-input" value={tenant.tenant_id} onChange={(e) => setTenant({ ...tenant, tenant_id: e.target.value })} /></Field><Field label="Companie"><Input data-testid="tenant-company-input" value={tenant.company_name} onChange={(e) => setTenant({ ...tenant, company_name: e.target.value })} /></Field><Field label="CUI"><Input data-testid="tenant-cui-input" value={tenant.cui} onChange={(e) => setTenant({ ...tenant, cui: e.target.value })} /></Field><Field label="Limită sucursale"><Input data-testid="tenant-branch-limit-input" type="number" min="1" value={tenant.max_branches_allowed} onChange={(e) => setTenant({ ...tenant, max_branches_allowed: e.target.value })} /></Field></div><Button className="mt-4" data-testid="create-tenant-button" disabled={!tenant.tenant_id || !tenant.company_name} onClick={createTenant}><Plus className="mr-1 h-4 w-4" />Creează tenant</Button></Panel><Panel title="Punct de lucru nou" testid="create-branch-panel"><div className="grid gap-3 sm:grid-cols-2"><Field label="Tenant"><NativeSelect data-testid="branch-tenant-select" value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">—</option>{tenants.map((item) => <option key={item.id} value={item.id}>{item.company_name}</option>)}</NativeSelect></Field><Field label="ID sucursală"><Input data-testid="branch-id-input" value={branch.branch_id} onChange={(e) => setBranch({ ...branch, branch_id: e.target.value })} /></Field><Field label="Nume sucursală"><Input data-testid="branch-name-input" value={branch.branch_name} onChange={(e) => setBranch({ ...branch, branch_name: e.target.value })} /></Field><Field label="Adresă"><Input data-testid="branch-address-input" value={branch.address} onChange={(e) => setBranch({ ...branch, address: e.target.value })} /></Field></div><Button className="mt-4" data-testid="create-branch-button" disabled={!selected || !branch.branch_id || !branch.branch_name} onClick={createBranch}><Building2 className="mr-1 h-4 w-4" />Creează punct de lucru</Button></Panel></div><Panel className="mt-4" title="Tenants activi" testid="tenant-list-panel"><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-sm" data-testid="tenant-list-table"><thead><tr className="border-b text-left text-xs uppercase text-muted-foreground"><th className="px-2 py-2">Companie</th><th>Plan</th><th>Limită sucursale</th><th>Status</th></tr></thead><tbody>{tenants.map((item) => <tr key={item.id} className="border-b"><td className="px-2 py-2"><span className="font-semibold">{item.company_name}</span><div className="font-mono text-xs text-muted-foreground">{item.id}</div></td><td>{item.subscription_plan}</td><td>{item.max_branches_allowed}</td><td>{item.status}</td></tr>)}</tbody></table></div></Panel></div>;
}