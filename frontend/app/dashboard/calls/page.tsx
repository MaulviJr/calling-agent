import PageHeading from "@/components/dashboard/PageHeading";
import Screen from "@/components/calls/CallsTable";

export const metadata = { title: "Calls | Ava" };

export default function Page() {
  return (
    <>
      <PageHeading
        title="Calls"
        description="Every conversation, with the details that matter."
      />
      <Screen />
    </>
  );
}
