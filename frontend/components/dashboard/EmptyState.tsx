export default function EmptyState({
  title,
  text,
}: {
  title: string;
  text: string;
}) {
  return (
    <div className="empty">
      <span aria-hidden="true">◌</span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
