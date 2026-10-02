import PageHeading from "@/components/dashboard/PageHeading";
import Screen from "@/components/appointments/AppointmentsTable";

export const metadata = { title: "Appointments | Ava" };

export default function Page() {
  return (
    <>
      <PageHeading
        title="Appointments"
        description="Keep your schedule and your team in sync."
      />
      <Screen />
    </>
  );
}
