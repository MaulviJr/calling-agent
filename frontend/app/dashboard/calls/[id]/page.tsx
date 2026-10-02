import PageHeading from "@/components/dashboard/PageHeading";
import CallDetails from "@/components/calls/CallDetails";

export const metadata = { title: "Call details | Ava" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <PageHeading
        title="Call details"
        description="The summary and transcript of this conversation."
      />
      <CallDetails id={id} />
    </>
  );
}
