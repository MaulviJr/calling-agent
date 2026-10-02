"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="p-8">
      <h1>Unable to open the workspace</h1>
      <p>Check that the Ava backend is running, then try again.</p>
      <button onClick={reset}>Try again</button>
    </main>
  );
}
