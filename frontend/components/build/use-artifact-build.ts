"use client";

import { useEffect } from "react";
import { useAgent } from "@/components/agent/agent-context";
import {
  ArtifactBuildItem,
  ArtifactBuildState,
  BuildElement,
} from "@/lib/build";

export type { ArtifactBuildItem, ArtifactBuildState, BuildElement };

export function useArtifactBuild(executionId: string | undefined) {
  const { state, dispatch } = useAgent();

  useEffect(() => {
    if (!executionId) return;
    if (state.executionId !== executionId) {
      dispatch({ type: "setExecutionId", value: executionId });
      if (state.build?.executionId !== executionId) {
        dispatch({ type: "resetBuild" });
      }
    }
  }, [executionId, state.executionId, state.build?.executionId, dispatch]);

  if (!executionId || state.executionId !== executionId) return null;
  return state.build;
}
