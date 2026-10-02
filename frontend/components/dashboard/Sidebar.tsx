"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";
import Brand from "./Brand";
import Notice from "./Notice";

const links = [
  { href: "/dashboard", title: "Overview", icon: "◫" },
  { href: "/dashboard/calls", title: "Calls", icon: "◷" },
  { href: "/dashboard/appointments", title: "Appointments", icon: "▦" },
  { href: "/dashboard/messages", title: "Messages", icon: "▤" },
  { href: "/dashboard/settings", title: "Settings", icon: "⚙" },
  { href: "/dashboard/demo", title: "Talk to Ava", icon: "◉" },
];

export default function Sidebar({ user }: { user: User }) {
  const pathname = usePathname();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      await api("/logout", "POST");
      router.replace("/login");
      router.refresh();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside>
      <Brand />
      <p className="workspace-label">CLINIC WORKSPACE</p>
      <nav aria-label="Dashboard navigation">
        {links.map((link) => {
          const active =
            pathname === link.href ||
            (link.href !== "/dashboard" &&
              pathname.startsWith(`${link.href}/`));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={active ? "active" : ""}
              aria-current={active ? "page" : undefined}
            >
              <span aria-hidden="true">{link.icon}</span>
              {link.title}
              {link.title === "Talk to Ava" && <small>DEMO</small>}
            </Link>
          );
        })}
      </nav>
      {error && <Notice text={error} />}
      <div className="sidebar-bottom">
        <div className="avatar">{user.email[0].toUpperCase()}</div>
        <div>
          <strong>Clinic team</strong>
          <small>{user.email}</small>
        </div>
        <button aria-label="Sign out" onClick={signOut} disabled={busy}>
          ↗
        </button>
      </div>
    </aside>
  );
}
