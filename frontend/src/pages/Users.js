import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { useAuth } from "@/context/AuthContext";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PageHeader, Panel, Loading, Field, NativeSelect, ROLE_LABELS } from "@/components/common";

function UserDialog({ state, setState, onSaved }) {
  const { tr } = useLang();
  const f = state.form;
  const set = (k, v) => setState({ ...state, form: { ...f, [k]: v } });
  const save = async () => {
    try {
      state.id ? await api.put(`/users/${state.id}`, f) : await api.post("/users", f);
      toast.success(tr("Utilizator salvat", "User saved"));
      onSaved();
      setState({ ...state, open: false });
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open={state.open} onOpenChange={(o) => setState({ ...state, open: o })}>
      <DialogContent data-testid="user-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{state.id ? tr("Editare utilizator", "Edit user") : tr("Utilizator nou", "New user")}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <Field label={tr("Nume", "Name")}><Input data-testid="user-name-input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Email"><Input data-testid="user-email-input" type="email" disabled={!!state.id} value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label={tr("Rol", "Role")}>
            <NativeSelect data-testid="user-role-select" value={f.role} onChange={(e) => set("role", e.target.value)}>
              {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])}</option>)}
            </NativeSelect>
          </Field>
          <Field label={state.id ? tr("Parolă nouă (opțional)", "New password (optional)") : tr("Parolă (min. 8)", "Password (min 8)")}>
            <Input data-testid="user-password-input" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} />
          </Field>
          <label className="flex items-center gap-2 text-sm"><Switch data-testid="user-active-switch" checked={f.active} onCheckedChange={(v) => set("active", v)} />{tr("Activ", "Active")}</label>
        </div>
        <DialogFooter><Button data-testid="user-save-button" onClick={save}>{tr("Salvează", "Save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Users() {
  const { tr } = useLang();
  const { user: me } = useAuth();
  const { data, reload } = useApi("/users");
  const { data: logs } = useApi("/audit");
  const blank = { name: "", email: "", role: "receptioner", password: "", active: true };
  const [dlg, setDlg] = useState({ open: false, id: null, form: blank });
  const del = async (u) => {
    if (!window.confirm(tr(`Ștergeți ${u.email}?`, `Delete ${u.email}?`))) return;
    try {
      await api.delete(`/users/${u.id}`);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div data-testid="users-page">
      <PageHeader eyebrow="RBAC · ISO 27001 · GDPR" title={tr("Utilizatori & audit", "Users & audit")}
        actions={<Button data-testid="add-user-button" onClick={() => setDlg({ open: true, id: null, form: blank })}><Plus className="mr-1 h-4 w-4" />{tr("Utilizator", "User")}</Button>} />
      <Tabs defaultValue="users">
        <TabsList><TabsTrigger value="users" data-testid="users-tab-users">{tr("Utilizatori", "Users")}</TabsTrigger><TabsTrigger value="audit" data-testid="users-tab-audit">Audit log</TabsTrigger></TabsList>
        <TabsContent value="users">
          <Panel>
            {!data ? <Loading /> : (
              <table className="w-full text-sm" data-testid="users-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Nume", "Name")}</th><th className="px-2">Email</th><th className="px-2">{tr("Rol", "Role")}</th><th className="px-2">{tr("Module", "Modules")}</th><th className="px-2">Status</th><th />
              </tr></thead><tbody>
                {data.map((u) => (
                  <tr key={u.id} className="h-11 border-b border-border/50" data-testid={`user-row-${u.email}`}>
                    <td className="px-2 font-medium">{u.name}</td><td className="px-2 font-mono text-xs">{u.email}</td>
                    <td className="px-2"><span className="rounded-sm bg-primary/10 px-2 py-0.5 text-[11px] font-bold uppercase text-primary">{tr(...(ROLE_LABELS[u.role] || [u.role, u.role]))}</span></td>
                    <td className="px-2 text-[11px] text-muted-foreground">{u.permissions.join(" · ")}</td>
                    <td className="px-2 text-xs">{u.active ? <span className="text-emerald-500">{tr("Activ", "Active")}</span> : <span className="text-rose-500">{tr("Inactiv", "Inactive")}</span>}</td>
                    <td className="px-2 text-right">
                      <Button variant="ghost" size="icon" data-testid={`edit-user-${u.email}`} onClick={() => setDlg({ open: true, id: u.id, form: { name: u.name, email: u.email, role: u.role, password: "", active: u.active } })}><Pencil className="h-4 w-4" /></Button>
                      {u.id !== me.id && <Button variant="ghost" size="icon" data-testid={`delete-user-${u.email}`} onClick={() => del(u)}><Trash2 className="h-4 w-4 text-rose-500" /></Button>}
                    </td>
                  </tr>
                ))}
              </tbody></table>
            )}
          </Panel>
        </TabsContent>
        <TabsContent value="audit">
          <Panel>
            <div className="max-h-[65vh] overflow-y-auto">
              <table className="w-full text-sm" data-testid="audit-table"><tbody>
                {(logs || []).map((l) => (
                  <tr key={l.id} className="h-9 border-b border-border/50"><td className="font-mono text-xs">{dt(l.at)}</td><td className="text-xs">{l.user_email}</td>
                    <td><span className="font-mono text-[11px] uppercase text-primary">{l.action}</span></td><td className="text-xs">{l.entity}</td><td className="font-mono text-xs text-muted-foreground">{l.details}</td></tr>
                ))}
              </tbody></table>
            </div>
          </Panel>
        </TabsContent>
      </Tabs>
      <UserDialog state={dlg} setState={setDlg} onSaved={reload} />
    </div>
  );
}
