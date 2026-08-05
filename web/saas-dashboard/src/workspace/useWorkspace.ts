import { useContext } from "react";
import { WorkspaceContext } from "./WorkspaceContext";

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
