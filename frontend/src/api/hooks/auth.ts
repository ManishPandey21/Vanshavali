import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiRequest, ApiError } from "../client";
import type { UserOut } from "../types";
import type { components } from "../schema";

export const authKeys = { me: ["auth", "me"] as const };

/** Current user, or `null` when signed out (a 401 here is not an error). */
export function useMe() {
  return useQuery<UserOut | null>({
    queryKey: authKeys.me,
    queryFn: async () => {
      try {
        return await apiRequest<UserOut>("/auth/me", { skipAuthRedirect: true });
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["LoginIn"]) =>
      apiRequest<UserOut>("/auth/login", { method: "POST", body, skipAuthRedirect: true }),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(authKeys.me, user);
    },
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["RegisterIn"]) =>
      apiRequest<UserOut>("/auth/register", { method: "POST", body, skipAuthRedirect: true }),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(authKeys.me, user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest<unknown>("/auth/logout", { method: "POST", body: {}, skipAuthRedirect: true }),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(authKeys.me, null);
    },
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["ProfileUpdateIn"]) => api.patch<UserOut>("/auth/me", body),
    onSuccess: (user) => qc.setQueryData(authKeys.me, user),
  });
}
