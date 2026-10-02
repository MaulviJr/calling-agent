import PageHeading from "@/components/dashboard/PageHeading";
import Screen from "@/components/settings/SettingsForm";

export const metadata = { title: "Settings | Ava" };

export default function Page() {
  return (
    <>
      <PageHeading
        title="Settings"
        description="Make Ava feel at home in your business."
      />
      <Screen />
    </>
  );
}
