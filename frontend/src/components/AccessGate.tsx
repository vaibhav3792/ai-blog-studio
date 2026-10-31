import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function AccessGate() {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(code),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="max-w-sm">
      <h1 className="mb-2 font-serif text-2xl font-semibold tracking-tight">Access code needed</h1>
      <p className="mb-4 text-muted">This studio uses shared API keys, so it is limited to people with the code.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (code.trim()) login.mutate();
        }}
      >
        <label htmlFor="code" className="sr-only">Access code</label>
        <input
          id="code"
          type="password"
          autoComplete="current-password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="w-full rounded border border-rule bg-panel p-3"
        />
        <button
          type="submit"
          disabled={!code.trim() || login.isPending}
          className="mt-3 rounded bg-ink px-4 py-2 font-medium text-paper disabled:opacity-40"
        >
          {login.isPending ? "Checking" : "Continue"}
        </button>
        {login.isError ? <p className="mt-2 text-sm text-bad">{(login.error as Error).message}</p> : null}
      </form>
    </div>
  );
}
