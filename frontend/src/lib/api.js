import axios from "axios";
import { useCallback, useEffect, useState } from "react";

export const API_URL = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_URL, withCredentials: true });

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const cfg = err.config;
    if (
      err.response?.status === 401 &&
      cfg &&
      !cfg._retry &&
      !cfg.url?.includes("/auth/")
    ) {
      cfg._retry = true;
      try {
        await axios.post(`${API_URL}/auth/refresh`, {}, { withCredentials: true });
        return api(cfg);
      } catch {
        // The protected route redirects unauthenticated users after refresh failure.
      }
    }
    return Promise.reject(err);
  }
);

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || "Eroare";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  return d.msg || String(d);
}

export function useApi(path) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const r = await api.get(path);
      setData(r.data);
      setError(null);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, setData, loading, error, reload };
}

export async function downloadFile(path, filename) {
  const r = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
