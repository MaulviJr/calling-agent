export default function MetricCard({
  title,
  value,
  description,
}: {
  title: string;
  value: string | number;
  description: string;
}) {
  return (
    <article>
      <span>{title}</span>
      <h2>{value}</h2>
      <small>{description}</small>
    </article>
  );
}
