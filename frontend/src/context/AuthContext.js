import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  const loadUser = useCallback(async () => {
    try {
      const response = await api.get("/auth/me");
      setUser(response.data);
    } catch {
      setUser(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    const handleExpiredSession = () => setUser(false);
    window.addEventListener("performa-auth-expired", handleExpiredSession);
    return () => window.removeEventListener("performa-auth-expired", handleExpiredSession);
  }, []);

  const login = useCallback(async (email, password) => {
    await api.post("/auth/login", { email, password });
    const refreshed = await api.get("/auth/me");
    setUser(refreshed.data);
    return refreshed.data;
  }, []);

  const logout = useCallback(async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(false);
  }, []);

  const switchBranch = useCallback(async (branchId) => {
    await api.post("/auth/active-branch", { branch_id: branchId });
    const refreshed = await api.get("/auth/me");
    setUser(refreshed.data);
    window.location.reload();
    return refreshed.data;
  }, []);

  const changeInitialPassword = useCallback(async (currentPassword, newPassword) => {
    const { data } = await api.post("/auth/change-initial-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
    setUser(data.user);
    return data.user;
  }, []);

  const can = useCallback((module) => !!user && user.permissions?.includes(module), [user]);
  const value = useMemo(
    () => ({ user, login, logout, switchBranch, changeInitialPassword, can }),
    [user, login, logout, switchBranch, changeInitialPassword, can],
  );

  return (
    <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
