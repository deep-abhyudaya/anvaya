"use client";

import { createAuthClient } from "better-auth/react";
import { organizationClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL:
    process.env.NEXT_PUBLIC_AUTH_URL ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000"),
  basePath: "/api/auth",
  fetchOptions: {
    credentials: "include",
  },
  plugins: [organizationClient()],
});

export type SessionPayload = {
  user: {
    id: string;
    name: string;
    email: string;
    emailVerified: boolean;
    image?: string | null;
    createdAt: Date;
    updatedAt: Date;
  };
  session: {
    id: string;
    token: string;
    userId: string;
    expiresAt: Date;
    activeOrganizationId?: string;
  };
};

type UseSessionResult = {
  data: SessionPayload | null;
  isPending: boolean;
  error: { message: string } | null;
  refetch: (params?: { query?: Record<string, unknown> }) => Promise<void>;
};

export const useSession = authClient.useSession as unknown as () => UseSessionResult;
