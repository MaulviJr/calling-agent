export default function PageHeading({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">YOUR RECEPTION, SIMPLIFIED</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <span className="subtle-chip">Staff workspace</span>
    </div>
  );
}
