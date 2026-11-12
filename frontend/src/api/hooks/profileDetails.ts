import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  AddressIn,
  AddressOut,
  AddressUpdate,
  PersonContactIn,
  PersonContactOut,
  ContactReveal,
  ContactUpdate,
  Message,
  MoveAddressIn,
  MoveAddressOut,
  Page,
  RevisionSnapshot,
} from "../types";

const base = (treeId: string, personId: string) => `/trees/${treeId}/people/${personId}`;
const keys = {
  addresses: (treeId: string, personId: string) => ["tree", treeId, "person", personId, "addresses"] as const,
  contacts: (treeId: string, personId: string) => ["tree", treeId, "person", personId, "contacts"] as const,
};

export function usePersonAddresses(treeId: string, personId: string) {
  return useQuery({
    queryKey: keys.addresses(treeId, personId),
    queryFn: () => api.get<Page<AddressOut>>(`${base(treeId, personId)}/addresses`),
    retry: false,
  });
}

export function useMoveAddress(treeId: string, personId: string, addressId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MoveAddressIn) =>
      api.post<MoveAddressOut>(`${base(treeId, personId)}/addresses/${addressId}/move`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.addresses(treeId, personId) }),
  });
}

export function useAddressHistory(treeId: string, personId: string, addressId: string | null) {
  return useQuery({
    queryKey: [...keys.addresses(treeId, personId), addressId ?? "", "history"],
    queryFn: () =>
      api.get<Page<RevisionSnapshot>>(`${base(treeId, personId)}/addresses/${addressId}/history`),
    enabled: !!addressId,
  });
}

export function useCreateAddress(treeId: string, personId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddressIn) => api.post<AddressOut>(`${base(treeId, personId)}/addresses`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.addresses(treeId, personId) }),
  });
}

export function useUpdateAddress(treeId: string, personId: string, addressId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddressUpdate) => api.patch<AddressOut>(`${base(treeId, personId)}/addresses/${addressId}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.addresses(treeId, personId) }),
  });
}

export function useDeleteAddress(treeId: string, personId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, revision }: { id: string; revision: number }) =>
      api.del<Message>(`${base(treeId, personId)}/addresses/${id}`, { revision }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.addresses(treeId, personId) }),
  });
}

export function usePersonContacts(treeId: string, personId: string) {
  return useQuery({
    queryKey: keys.contacts(treeId, personId),
    queryFn: () => api.get<Page<PersonContactOut>>(`${base(treeId, personId)}/contacts`),
    retry: false,
  });
}

export function useCreateContact(treeId: string, personId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PersonContactIn) => api.post<PersonContactOut>(`${base(treeId, personId)}/contacts`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts(treeId, personId) }),
  });
}

export function useUpdateContact(treeId: string, personId: string, contactId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ContactUpdate) => api.patch<PersonContactOut>(`${base(treeId, personId)}/contacts/${contactId}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts(treeId, personId) }),
  });
}

export function useRevealContact(treeId: string, personId: string) {
  return useMutation({
    mutationFn: (contactId: string) => api.get<ContactReveal>(`${base(treeId, personId)}/contacts/${contactId}/reveal`),
  });
}

export function useDeleteContact(treeId: string, personId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, revision }: { id: string; revision: number }) =>
      api.del<Message>(`${base(treeId, personId)}/contacts/${id}`, { revision }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.contacts(treeId, personId) }),
  });
}
