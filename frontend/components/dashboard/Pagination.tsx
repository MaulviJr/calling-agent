export default function Pagination({
  offset,
  count,
  onChange,
}: {
  offset: number;
  count: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="pagination">
      <button
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - 50))}
      >
        ← Previous
      </button>
      <span>Page {offset / 50 + 1}</span>
      <button disabled={count < 50} onClick={() => onChange(offset + 50)}>
        Next →
      </button>
    </div>
  );
}
