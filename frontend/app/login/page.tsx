import LoginForm from "@/components/LoginForm";
import Brand from "@/components/dashboard/Brand";

export default function LoginPage() {
  return (
    <main className="login">
      <div className="login-story">
        <Brand />
        <p className="eyebrow">YOUR CLINIC, CONNECTED</p>
        <h1>
          A little more care.
          <br />A little less admin.
        </h1>
        <p>
          A calm place to manage the conversations,
          <br />
          appointments and follow-ups that matter.
        </p>
        <div className="rings" aria-hidden="true">
          <div />
          <div />
          <div />
        </div>
      </div>
      <LoginForm />
    </main>
  );
}
