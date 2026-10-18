import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { KeyRound, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/common";
import { Input } from "@/components/ui/input";

export default function InitialPassword() {
  const { user, changeInitialPassword, logout } = useAuth();
  const nav = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!user?.must_change_password) return <Navigate to="/" replace />;

  const submit = async (event) => {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setError("Confirmarea nu corespunde parolei noi.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await changeInitialPassword(currentPassword, newPassword);
      toast.success("Parola a fost schimbată.");
      nav("/");
    } catch (requestError) {
      setError(errMsg(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="grid-bg flex min-h-screen items-center justify-center p-6">
      <form
        className="w-full max-w-md rounded-md border bg-card p-6 shadow-2xl fade-up sm:p-8"
        data-testid="initial-password-form"
        onSubmit={submit}
      >
        <div className="mb-6 flex items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded bg-primary"
            data-testid="initial-password-icon"
          >
            <KeyRound className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1
              className="font-heading text-3xl font-extrabold uppercase"
              data-testid="initial-password-title"
            >
              Securizează contul
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Schimbă parola inițială înainte de a accesa spațiul de lucru.
            </p>
          </div>
        </div>

        <div className="mb-5 flex gap-2 border-l-2 border-primary bg-primary/5 p-3 text-sm">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span data-testid="initial-password-account-email">{user.email}</span>
        </div>

        <div className="space-y-4">
          <Field label="Parola inițială">
            <Input
              data-testid="initial-password-current-input"
              type="password"
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </Field>
          <Field label="Parola nouă">
            <Input
              data-testid="initial-password-new-input"
              type="password"
              minLength="8"
              required
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </Field>
          <Field label="Confirmă parola nouă">
            <Input
              data-testid="initial-password-confirm-input"
              type="password"
              minLength="8"
              required
              autoComplete="new-password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </Field>
        </div>

        {error && (
          <div
            className="mt-4 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            data-testid="initial-password-error"
          >
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            data-testid="initial-password-logout-button"
            onClick={async () => {
              await logout();
              nav("/login");
            }}
          >
            Ieșire
          </Button>
          <Button
            type="submit"
            disabled={busy}
            data-testid="initial-password-submit-button"
          >
            {busy ? "Se salvează…" : "Salvează parola"}
          </Button>
        </div>
      </form>
    </main>
  );
}