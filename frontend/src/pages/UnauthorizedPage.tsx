import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { AuthCard } from "@/components/auth/AuthCard";

export function UnauthorizedPage() {
  const { isAuthenticated } = useAuth();

  return (
    <AuthCard>
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-stone-100">
          <svg
            className="h-5 w-5 text-stone-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.75}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
            />
          </svg>
        </div>
        <h1 className="text-lg font-semibold text-zinc-800">Access denied</h1>
        <p className="mt-2 text-sm text-stone-600">You don't have permission to view this page.</p>
        <Link
          to={isAuthenticated ? "/home" : "/login"}
          className="mt-6 inline-block text-sm text-amber-700 underline underline-offset-2 hover:text-amber-800"
        >
          {isAuthenticated ? "Back to home" : "Sign in"}
        </Link>
      </div>
    </AuthCard>
  );
}
