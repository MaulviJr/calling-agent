import type { TranscriptTurn } from "@/lib/types";

export default function Transcript({ turns }: { turns: TranscriptTurn[] }) {
  return (
    <section aria-label="Transcript">
      <h3>Transcript</h3>
      {turns.length === 0 && <p>No transcript has been recorded.</p>}
      {turns.map((turn) => (
        <div key={turn.id} className={`turn ${turn.role}`}>
          <strong>{turn.role === "user" ? "Caller" : "Ava"}</strong>
          <p>{turn.text}</p>
          {turn.delivery === "interrupted" && (
            <small>
              Playback interrupted — caller may not have heard all of this.
            </small>
          )}
        </div>
      ))}
    </section>
  );
}
