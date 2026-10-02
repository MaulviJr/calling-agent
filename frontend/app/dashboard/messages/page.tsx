import PageHeading from "@/components/dashboard/PageHeading";
import Screen from "@/components/messages/MessageList";

export const metadata = { title: "Messages | Ava" };

export default function Page() {
  return (
    <>
      <PageHeading
        title="Messages"
        description="A thoughtful follow-up starts here."
      />
      <Screen />
    </>
  );
}
