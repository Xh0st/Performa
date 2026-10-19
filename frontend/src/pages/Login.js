import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLang } from "@/lib/prefs";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/common";

const HERO = "https://images.unsplash.com/photo-1615906655593-ad0386982a0f?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600";

export default function Login() {
  const { login, user } = useAuth();
  const { tr, lang, setLang, theme } = useLang();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={user.must_change_password ? "/change-initial-password" : "/"} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const loggedInUser = await login(email, password);
      nav(loggedInUser.must_change_password ? "/change-initial-password" : "/");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.2fr_1fr]">
      <div className="relative hidden overflow-hidden lg:block">
        <img src={HERO} alt="Atelier service auto" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/60 to-slate-950/20" />
        <div className="absolute bottom-0 left-0 right-0 p-12 text-white">
          <div
            className="mb-3 font-mono text-xs uppercase tracking-[0.3em] text-orange-400"
            data-testid="login-brand-name"
          >
            ERP · Performa Auto · România
          </div>
          <h1 className="font-heading text-5xl font-extrabold uppercase leading-[0.95] tracking-tight xl:text-6xl">
            {tr("Atelierul tău,", "Your workshop,")}<br />{tr("sub control total.", "fully under control.")}
          </h1>
          <p className="mt-4 max-w-lg text-sm text-slate-300">
            {tr("Recepție, comenzi de lucru, devize, magazie, facturare e-Factura și productivitate mecanici — într-o singură platformă.",
              "Reception, work orders, quotes, warehouse, e-Invoice billing and mechanic productivity — in one platform.")}
          </p>
        </div>
      </div>
      <div className="grid-bg flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm rounded-md border bg-card p-8 shadow-2xl fade-up" data-testid="login-form">
          <div className="mb-8 flex items-center justify-between">
            <img
              src={theme === "dark" ? "/performa-logo-dark.png" : "/performa-logo.png"}
              alt="Performa Auto"
              className={`h-12 object-contain ${theme === "dark" ? "w-28" : "w-12"}`}
              data-testid="login-brand-mark"
            />
            <Button type="button" variant="outline" size="sm" className="font-mono" data-testid="login-language-toggle" onClick={() => setLang(lang === "ro" ? "en" : "ro")}>
              {lang.toUpperCase()}
            </Button>
          </div>
          <h2 className="font-heading text-3xl font-extrabold uppercase tracking-tight">{tr("Autentificare", "Sign in")}</h2>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">{tr("Conturile sunt create de administrator.", "Accounts are created by the administrator.")}</p>
          <div className="space-y-4">
            <Field label="Email">
              <Input data-testid="login-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </Field>
            <Field label={tr("Parolă", "Password")}>
              <Input data-testid="login-password-input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </Field>
            {error && <div data-testid="login-error" className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
            <Button data-testid="login-submit-button" type="submit" className="w-full active:scale-95" disabled={busy}>
              {busy ? "…" : tr("Intră în cont", "Sign in")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
