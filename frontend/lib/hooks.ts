"use client";

import { useQuery } from "@tanstack/react-query";
import { AnvayaAPI } from "./api";

export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: AnvayaAPI.metrics,
  });
}

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: AnvayaAPI.incidents,
  });
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: ["incident", id],
    queryFn: () => AnvayaAPI.incident(id),
    enabled: !!id,
  });
}

export function useDemo() {
  return useQuery({
    queryKey: ["demo"],
    queryFn: AnvayaAPI.demo,
    enabled: false,
  });
}
