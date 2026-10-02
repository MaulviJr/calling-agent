import { requireUser } from "@/lib/auth";
import Sidebar from "@/components/dashboard/Sidebar";
import Header from "@/components/dashboard/Header";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();
  return (
    <div className="shell">
      <Sidebar user={user} />
      <main className="content">
        <Header />
        <section className="page">{children}</section>
      </main>
    </div>
  );
}
