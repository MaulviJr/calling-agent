"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export default function Header() {
  const pathname = usePathname();
  const [today, setToday] = useState("");
  const segment = pathname.split("/")[2];
  const titles: { [key: string]: string } = {
    calls: "Calls",
    appointments: "Appointments",
    messages: "Messages",
    settings: "Settings",
    demo: "Talk to Ava",
  };
  useEffect(() => {
    setToday(
      new Date().toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      }),
    );
  }, []);
  return (
    <header>
      <span>
        Workspace{" "}
        <span className="muted">/ {titles[segment] || "Overview"}</span>
      </span>
      <span className="today">{today}</span>
    </header>
  );
}
