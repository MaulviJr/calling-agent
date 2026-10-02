export default function Notice({ text }: { text: string }) {
  return (
    <p className="error" role="alert">
      {text}
    </p>
  );
}
