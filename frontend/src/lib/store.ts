"use client";
/**
 * Global auth + site store.
 * FIX: SITE_ID no longer hardcoded — stored in user context (site_id from first camera, or 1).
 * The active siteId is persisted to sessionStorage so page refreshes keep context.
 */
import { create } from "zustand";
import type { User } from "@/types";
import { authApi, tokenStore } from "@/lib/api";

const isBrowser = () => typeof window !== "undefined";

interface AuthState {
  user:       User | null;
  loading:    boolean;
  siteId:     number;        // active site — replaces all hardcoded SITE_ID = 1
  setSiteId:  (id: number) => void;
  login:      (email: string, password: string) => Promise<void>;
  logout:     () => void;
  hydrate:    () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user:    null,
  loading: true,
  siteId:  isBrowser() ? Number(sessionStorage.getItem("sl_site_id") ?? "1") : 1,

  setSiteId: (id: number) => {
    if (isBrowser()) sessionStorage.setItem("sl_site_id", String(id));
    set({ siteId: id });
  },

  login: async (email: string, password: string) => {
    await authApi.login(email, password);
    const user = await authApi.me();
    set({ user, loading: false });
  },

  logout: () => {
    authApi.logout();
    set({ user: null, loading: false });
  },

  hydrate: async () => {
    const token = tokenStore.get();
    if (!token) { set({ loading: false }); return; }
    try {
      const user = await authApi.me();
      const storedSite = isBrowser() ? Number(sessionStorage.getItem("sl_site_id") ?? "1") : 1;
      set({ user, loading: false, siteId: storedSite || 1 });
    } catch {
      tokenStore.clear();
      set({ user: null, loading: false });
    }
  },
}));
