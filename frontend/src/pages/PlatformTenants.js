import { useState } from "react";
import { Building2, Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, useApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, Loading, NativeSelect, PageHeader, Panel } from "@/components/common";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const EMPTY_TENANT = {
  company_name: "",
  cui: "",
  admin_email: "",
  initial_password: "",
  subscription_plan: "BASIC",
};

const EMPTY_BRANCH = {
  branch_id: "",
  branch_name: "",
  address: "",
  rar_authorization_code: "",
  is_main_branch: false,
};

export default function PlatformTenants() {
  const { user } = useAuth();
  const { data: tenants, reload } = useApi(
    user?.platform_role === "SUPERADMIN" ? "/platform/tenants" : null,
    [user?.platform_role],
  );
  const [tenant, setTenant] = useState(EMPTY_TENANT);
  const [branch, setBranch] = useState(EMPTY_BRANCH);
  const [selected, setSelected] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [resetTarget, setResetTarget] = useState(null);
  const [temporaryPassword, setTemporaryPassword] = useState(null);

  if (!user || user.platform_role !== "SUPERADMIN") {
    return (
      <div className="p-8" data-testid="platform-access-denied">
        Acces rezervat Superadmin.
      </div>
    );
  }
  if (!tenants) return <Loading />;

  const createTenant = async () => {
    try {
      const response = await api.post("/platform/tenants", tenant);
      toast.success("Tenant și administrator creați");
      setTenant(EMPTY_TENANT);
      setSelected(response.data.id);
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  const createBranch = async () => {
    try {
      await api.post(`/platform/tenants/${selected}/branches`, branch);
      toast.success("Punct de lucru creat");
      setBranch(EMPTY_BRANCH);
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  const deleteTenant = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/platform/tenants/${deleteTarget.id}`, {
        data: { confirmation: deleteConfirmation },
      });
      toast.success("Tenant șters definitiv");
      setDeleteTarget(null);
      setDeleteConfirmation("");
      if (selected === deleteTarget.id) setSelected("");
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  const resetTenantAdminPassword = async () => {
    if (!resetTarget) return;
    try {
      const response = await api.post(
        `/platform/tenants/${resetTarget.id}/admin/reset-password`,
      );
      setTemporaryPassword(response.data);
      toast.success("Parola temporară a fost generată");
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  const closeResetDialog = () => {
    setResetTarget(null);
    setTemporaryPassword(null);
  };

  const copyTemporaryPassword = async () => {
    if (!temporaryPassword?.temporary_password) return;
    await navigator.clipboard.writeText(temporaryPassword.temporary_password);
    toast.success("Parola temporară a fost copiată");
  };

  return (
    <div data-testid="platform-tenants-page">
      <PageHeader
        eyebrow="Platformă · licențe · izolare"
        title="Superadmin · Tenants"
      />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Tenant nou" testid="create-tenant-panel">
          <p className="mb-4 text-sm text-muted-foreground" data-testid="tenant-id-generation-note">
            ID-ul tenantului și sediul principal sunt generate automat. BASIC include o
            sucursală, iar FULL include până la cinci.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Nume companie SRL">
              <Input
                data-testid="tenant-company-input"
                required
                value={tenant.company_name}
                onChange={(event) => setTenant({ ...tenant, company_name: event.target.value })}
              />
            </Field>
            <Field label="CUI">
              <Input
                data-testid="tenant-cui-input"
                required
                value={tenant.cui}
                onChange={(event) => setTenant({ ...tenant, cui: event.target.value })}
              />
            </Field>
            <Field label="Email administrator">
              <Input
                data-testid="tenant-admin-email-input"
                type="email"
                required
                value={tenant.admin_email}
                onChange={(event) => setTenant({ ...tenant, admin_email: event.target.value })}
              />
            </Field>
            <Field label="Parolă inițială">
              <Input
                data-testid="tenant-initial-password-input"
                type="password"
                minLength="8"
                required
                value={tenant.initial_password}
                onChange={(event) => setTenant({ ...tenant, initial_password: event.target.value })}
              />
            </Field>
            <Field label="Tip abonament">
              <NativeSelect
                data-testid="tenant-plan-select"
                value={tenant.subscription_plan}
                onChange={(event) => {
                  setTenant({ ...tenant, subscription_plan: event.target.value });
                }}
              >
                <option value="BASIC">BASIC · 1 sucursală</option>
                <option value="FULL">FULL · 5 sucursale</option>
              </NativeSelect>
            </Field>
          </div>
          <Button
            className="mt-4"
            data-testid="create-tenant-button"
            disabled={
              !tenant.company_name
              || !tenant.cui
              || !tenant.admin_email
              || tenant.initial_password.length < 8
            }
            onClick={createTenant}
          >
            <Plus className="mr-1 h-4 w-4" />
            Creează tenant
          </Button>
        </Panel>

        <Panel title="Punct de lucru nou" testid="create-branch-panel">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Tenant">
              <NativeSelect
                data-testid="branch-tenant-select"
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
              >
                <option value="">—</option>
                {tenants.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.company_name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="ID sucursală">
              <Input
                data-testid="branch-id-input"
                value={branch.branch_id}
                onChange={(event) => setBranch({ ...branch, branch_id: event.target.value })}
              />
            </Field>
            <Field label="Nume sucursală">
              <Input
                data-testid="branch-name-input"
                value={branch.branch_name}
                onChange={(event) => setBranch({ ...branch, branch_name: event.target.value })}
              />
            </Field>
            <Field label="Adresă">
              <Input
                data-testid="branch-address-input"
                value={branch.address}
                onChange={(event) => setBranch({ ...branch, address: event.target.value })}
              />
            </Field>
          </div>
          <Button
            className="mt-4"
            data-testid="create-branch-button"
            disabled={!selected || !branch.branch_id || !branch.branch_name}
            onClick={createBranch}
          >
            <Building2 className="mr-1 h-4 w-4" />
            Creează punct de lucru
          </Button>
        </Panel>
      </div>

      <Panel className="mt-4" title="Tenants activi" testid="tenant-list-panel">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-sm" data-testid="tenant-list-table">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="px-2 py-2">Companie</th>
                <th>CUI</th>
                <th>Email administrator</th>
                <th>Plan</th>
                <th>Limită sucursale</th>
                <th>Status</th>
                <th className="px-2 text-right">Acțiuni</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((item) => (
                <tr key={item.id} className="border-b">
                  <td className="px-2 py-2">
                    <span className="font-semibold" data-testid={`tenant-name-${item.id}`}>
                      {item.company_name}
                    </span>
                    <div className="font-mono text-xs text-muted-foreground">{item.id}</div>
                  </td>
                  <td data-testid={`tenant-cui-${item.id}`}>{item.cui || "—"}</td>
                  <td data-testid={`tenant-admin-email-${item.id}`}>
                    {item.admin_email || "—"}
                  </td>
                  <td data-testid={`tenant-plan-${item.id}`}>{item.subscription_plan}</td>
                  <td>{item.max_branches_allowed}</td>
                  <td data-testid={`tenant-status-${item.id}`}>{item.status}</td>
                  <td className="px-2 py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        data-testid={`reset-tenant-${item.id}-password-button`}
                        disabled={item.id === user.tenant_id || !item.admin_email}
                        title={
                          item.id === user.tenant_id
                            ? "Parola administratorului propriu nu poate fi resetată"
                            : "Generează o parolă temporară"
                        }
                        onClick={() => {
                          setResetTarget(item);
                          setTemporaryPassword(null);
                        }}
                      >
                        <KeyRound className="h-4 w-4" />
                        Resetare parolă
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        data-testid={`delete-tenant-${item.id}-button`}
                        disabled={item.id === user.tenant_id}
                        title={
                          item.id === user.tenant_id
                            ? "Tenantul curent nu poate fi șters"
                            : "Șterge tenant"
                        }
                        onClick={() => {
                          setDeleteTarget(item);
                          setDeleteConfirmation("");
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                        Șterge
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
            setDeleteConfirmation("");
          }
        }}
      >
        <AlertDialogContent data-testid="delete-tenant-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Șterge tenant definitiv</AlertDialogTitle>
            <AlertDialogDescription>
              Sunt șterse definitiv utilizatorii, sucursalele, datele operaționale și configurările
              asociate. Scrie exact numele companiei pentru confirmare.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            data-testid="delete-tenant-confirmation-input"
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.target.value)}
            placeholder={deleteTarget?.company_name || ""}
          />
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-tenant-cancel-button">
              Renunță
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="delete-tenant-confirm-button"
              disabled={deleteConfirmation !== deleteTarget?.company_name}
              onClick={deleteTenant}
            >
              Șterge definitiv
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={Boolean(resetTarget)}
        onOpenChange={(open) => {
          if (!open) closeResetDialog();
        }}
      >
        <DialogContent data-testid="reset-tenant-password-dialog">
          {!temporaryPassword ? (
            <>
              <DialogHeader>
                <DialogTitle>Resetează parola administratorului</DialogTitle>
                <DialogDescription>
                  Se generează o parolă temporară pentru {resetTarget?.admin_email}. Administratorul
                  va fi obligat să o schimbe la următoarea conectare.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  data-testid="reset-tenant-password-cancel-button"
                  onClick={closeResetDialog}
                >
                  Renunță
                </Button>
                <Button
                  data-testid="reset-tenant-password-generate-button"
                  onClick={resetTenantAdminPassword}
                >
                  Generează parola temporară
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Parolă temporară generată</DialogTitle>
                <DialogDescription>
                  Comunic-o securizat la {temporaryPassword.admin_email}. Nu va mai fi afișată după
                  închiderea acestei ferestre.
                </DialogDescription>
              </DialogHeader>
              <Input
                data-testid="reset-tenant-temporary-password"
                value={temporaryPassword.temporary_password}
                readOnly
              />
              <DialogFooter>
                <Button
                  variant="outline"
                  data-testid="copy-tenant-temporary-password-button"
                  onClick={copyTemporaryPassword}
                >
                  <Copy className="h-4 w-4" />
                  Copiază parola
                </Button>
                <Button
                  data-testid="close-tenant-temporary-password-button"
                  onClick={closeResetDialog}
                >
                  Am notat parola
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}