import { SignUp } from "@clerk/clerk-react";

export function RegisterPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
          <p className="text-sm text-muted-foreground">Create your account</p>
        </div>
        <SignUp
          routing="hash"
          signInUrl="/login"
          fallbackRedirectUrl="/"
          appearance={{
            elements: {
              rootBox: "w-full",
              card: "shadow-none border rounded-lg p-6 bg-card",
              headerTitle: "hidden",
              headerSubtitle: "hidden",
            },
          }}
        />
      </div>
    </div>
  );
}
