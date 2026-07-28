import { useAuth } from "../auth/AuthProvider";
import { Navigate } from "react-router-dom";

interface RequireSystemAdminProps {
  children: React.ReactNode;
}

export function RequireSystemAdmin({ children }: RequireSystemAdminProps) {
  const { status, isSystemAdmin } = useAuth();

  if (status === "initializing") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2" style={{ borderColor: "var(--primary)" }} />
      </div>
    );
  }

  if (!isSystemAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
