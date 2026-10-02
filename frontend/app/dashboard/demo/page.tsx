import PageHeading from "@/components/dashboard/PageHeading";
import VoiceDemo from "@/components/voice/VoiceDemo";

export const metadata = { title: "Talk to Ava | Ava" };

export default function Page() {
  return (
    <>
      <PageHeading
        title="Talk to Ava"
        description="Try the same receptionist your callers will use."
      />
      <VoiceDemo />
    </>
  );
}
