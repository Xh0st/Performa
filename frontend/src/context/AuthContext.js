import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));
  }, []);
  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("erp_token", data.token);
    setUser(data.user);
    return data.user;
  };
  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("erp_token");
    setUser(false);
  };
  const can = (m) => !!user && user.permissions?.includes(m);
  return <AuthCtx.Provider value={{ user, login, logout, can }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
