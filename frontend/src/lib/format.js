const nf = new Intl.NumberFormat("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const money = (v, cur = "RON") => `${nf.format(Number(v || 0))} ${cur}`;
export const num = (v, d = 2) => Number(v || 0).toLocaleString("ro-RO", { maximumFractionDigits: d });
export const date = (s) => (s ? new Date(s).toLocaleDateString("ro-RO") : "—");
export const dt = (s) =>
  s ? new Date(s).toLocaleString("ro-RO", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const today = () => new Date().toISOString().slice(0, 10);
