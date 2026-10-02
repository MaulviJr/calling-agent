import PageHeading from "@/components/dashboard/PageHeading";
import Overview from "@/components/dashboard/Overview";

export const metadata = { title: "Overview | Ava" };

export default function DashboardPage() {
  return (
    <>
      <PageHeading
        title="Overview"
        description="A clear view of your clinic’s conversations."
      />
      <Overview />
    </>
  );
}
