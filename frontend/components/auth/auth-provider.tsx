"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, usePathname } from "next/navigation";
import { authClient, useSession } from "@/lib/auth-client";
import type { SessionPayload } from "@/lib/auth-client";
import { useOrganizations } from "@/lib/api";
import { trackStartupedEvent } from "@/lib/startuped";

type User = { id: string; name: string; email: string; image?: string | null };
type Organization = {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  role: string;
};

type AuthState = {
  session: SessionPayload | null;
  user: User | null;
  isLoading: boolean;
  activeOrganization: Organization | null;
  organizations: Organization[];
  signIn: (email: string, password: string) => Promise<{ error?: string }>;
  signUp: (name: string, email: string, password: string) => Promise<{ error?: string }>;
  signOut: () => Promise<void>;
  setActiveOrganization: (orgId: string) => Promise<void>;
  createOrganization: (data: {
    name: string;
    slug: string;
    logo?: string;
  }) => Promise<{ error?: string; id?: string }>;
};

const AuthCtx = createContext<AuthState | null>(null);

const publicPaths = ["/sign-in", "/sign-up", "/create-organization"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const {
    data: session,
    isPending: sessionLoading,
    refetch,
  } = useSession();

  const queryClient = useQueryClient();

  const user = session?.user ?? null;

  const { data: orgsData, isLoading: orgsLoading } = useOrganizations(!!user);
  const organizations = useMemo(() => (orgsData?.items as Organization[]) || [], [orgsData]);

  const activeOrganizationId = session?.session?.activeOrganizationId;
  const activeOrganization = useMemo(
    () => organizations.find((o) => o.id === activeOrganizationId) || organizations[0] || null,
    [organizations, activeOrganizationId],
  );

  const [isSigningOut, setIsSigningOut] = useState(false);
  const settingActiveRef = useRef(false);

  useEffect(() => {
    if (sessionLoading || orgsLoading || isSigningOut) return;

    if (!user) {
      if (!publicPaths.includes(pathname)) {
        router.push("/sign-in");
      }
      return;
    }

    if (publicPaths.includes(pathname)) {
      const target = organizations.length === 0 ? "/create-organization" : "/projects";
      if (pathname !== target) {
        router.push(target);
      }
    }
  }, [user, sessionLoading, orgsLoading, isSigningOut, pathname, router, organizations.length]);

  useEffect(() => {
    if (sessionLoading || orgsLoading || isSigningOut) return;
    if (!activeOrganizationId && organizations.length > 0 && !settingActiveRef.current) {
      settingActiveRef.current = true;
      authClient.organization
        .setActive({ organizationId: organizations[0].id })
        .then(() => refetch())
        .finally(() => {
          settingActiveRef.current = false;
        });
    }
  }, [
    activeOrganizationId,
    isSigningOut,
    orgsLoading,
    organizations,
    sessionLoading,
    refetch,
  ]);

  const signIn = async (email: string, password: string) => {
    trackStartupedEvent({
      name: "anvaya.auth.signin.started",
      description: "User started sign-in",
      type: "behavioral",
      strength: 15,
      value: "Low",
    });
    const { error } = await authClient.signIn.email({ email, password });
    trackStartupedEvent({
      name: error ? "anvaya.auth.signin.failed" : "anvaya.auth.signin.completed",
      description: error ? "Sign-in failed" : "User signed in",
      type: error ? "behavioral" : "conversion",
      strength: error ? 20 : 65,
      value: error ? "Medium" : "High",
      metadata: { surface: "auth", success: !error },
    });
    if (!error) await refetch();
    return { error: error?.message };
  };

  const signUp = async (name: string, email: string, password: string) => {
    trackStartupedEvent({
      name: "anvaya.auth.signup.started",
      description: "User started sign-up",
      type: "behavioral",
      strength: 15,
      value: "Low",
    });
    const { error } = await authClient.signUp.email({ name, email, password });
    trackStartupedEvent({
      name: error ? "anvaya.auth.signup.failed" : "anvaya.auth.signup.completed",
      description: error ? "Sign-up failed" : "User signed up",
      type: error ? "behavioral" : "conversion",
      strength: error ? 20 : 75,
      value: error ? "Medium" : "High",
      metadata: { surface: "auth", success: !error },
    });
    if (!error) await refetch();
    return { error: error?.message };
  };

  const signOut = async () => {
    setIsSigningOut(true);
    await authClient.signOut();
    trackStartupedEvent({
      name: "anvaya.auth.signout.completed",
      description: "User signed out",
      type: "behavioral",
      strength: 20,
      value: "Low",
    });
    await refetch();
    setIsSigningOut(false);
    router.push("/sign-in");
  };

  const setActiveOrganization = async (orgId: string) => {
    await authClient.organization.setActive({ organizationId: orgId });
    trackStartupedEvent({
      name: "anvaya.organization.switched",
      description: "User switched active organization",
      type: "behavioral",
      strength: 25,
      value: "Medium",
      metadata: { surface: "organization", organizationId: orgId },
    });
    await refetch();
  };

  const createOrganization = async (data: { name: string; slug: string; logo?: string }) => {
    const { data: org, error } = await authClient.organization.create({
      name: data.name,
      slug: data.slug,
      logo: data.logo || null,
    });
    trackStartupedEvent({
      name: error ? "anvaya.organization.create.failed" : "anvaya.organization.created",
      description: error ? "Organization creation failed" : "User created an organization",
      type: error ? "behavioral" : "conversion",
      strength: error ? 20 : 70,
      value: error ? "Medium" : "High",
      metadata: { surface: "organization", success: !error },
    });
    if (!error) {
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
      await refetch();
      return { id: org?.id };
    }
    return { error: error.message };
  };

  const value: AuthState = {
    session,
    user,
    isLoading: sessionLoading || orgsLoading || isSigningOut,
    activeOrganization,
    organizations,
    signIn,
    signUp,
    signOut,
    setActiveOrganization,
    createOrganization,
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
