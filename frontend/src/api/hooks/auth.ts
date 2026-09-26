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

type Message = components["schemas"]["Message"];

/** Registration never signs in: the server always answers 202 "check your email" (no enumeration). */
export function useRegister() {
  return useMutation({
    mutationFn: (body: components["schemas"]["RegisterIn"]) =>
      apiRequest<Message>("/auth/register", { method: "POST", body, skipAuthRedirect: true }),
  });
}

/** Opens an emailed verification link: marks the email verified and starts a session. */
export function useVerifyEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      apiRequest<UserOut>("/auth/verify-email", { method: "POST", body: { token }, skipAuthRedirect: true }),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(authKeys.me, user);
    },
  });
}

export function useResendVerification() {
  return useMutation({
    mutationFn: (email: string) =>
      apiRequest<Message>("/auth/resend-verification", { method: "POST", body: { email }, skipAuthRedirect: true }),
  });
}

export function useRequestPasswordReset() {
  return useMutation({
    mutationFn: (email: string) =>
      apiRequest<Message>("/auth/password-reset/request", { method: "POST", body: { email }, skipAuthRedirect: true }),
  });
}

export function useConfirmPasswordReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["PasswordResetConfirmIn"]) =>
      apiRequest<Message>("/auth/password-reset/confirm", { method: "POST", body, skipAuthRedirect: true }),
    onSuccess: () => {
      // every session was revoked server-side
      qc.clear();
      qc.setQueryData(authKeys.me, null);
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

/** External sign-in options this server offers (ADR-0012). Buttons for anything else stay hidden. */
export function useAuthProviders() {
  return useQuery({
    queryKey: ["auth", "providers"] as const,
    queryFn: () => apiRequest<components["schemas"]["ProvidersOut"]>("/auth/providers", { skipAuthRedirect: true }),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** Changes the password; the way out of a forced change (``must_change_password``). */
export function useChangePassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["PasswordChangeIn"]) => api.post<Message>("/auth/password", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.me }),
  });
}
