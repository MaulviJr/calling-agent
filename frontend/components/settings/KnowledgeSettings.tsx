"use client";

import { useState } from "react";
import type { KnowledgeEntry, StaffMember } from "@/lib/types";

function StaffEditor({
  member,
  onChange,
  onRemove,
}: {
  member: StaffMember;
  onChange: (changes: Partial<StaffMember>) => void;
  onRemove: () => void;
}) {
  // Keep unfinished separators while typing; persist only structured values.
  const [qualifications, setQualifications] = useState(
    member.qualifications.join(", "),
  );
  return (
    <div className="service">
      <label>
        Name
        <input
          required
          maxLength={120}
          value={member.name}
          onChange={(event) => onChange({ name: event.target.value })}
        />
      </label>
      <label>
        Role
        <input
          required
          maxLength={100}
          placeholder="Physiotherapist"
          value={member.role}
          onChange={(event) => onChange({ role: event.target.value })}
        />
      </label>
      <label>
        Qualifications (comma-separated)
        <input
          placeholder="PhD"
          value={qualifications}
          onChange={(event) => {
            setQualifications(event.target.value);
            onChange({
              qualifications: event.target.value
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            });
          }}
        />
      </label>
      <div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={member.active}
            onChange={(event) => onChange({ active: event.target.checked })}
          />
          Active
        </label>
        <button type="button" onClick={onRemove}>
          Remove staff
        </button>
      </div>
    </div>
  );
}

export default function KnowledgeSettings({
  staff,
  onStaffChange,
  entries,
  onChange,
}: {
  staff: StaffMember[];
  onStaffChange: (staff: StaffMember[]) => void;
  entries: KnowledgeEntry[];
  onChange: (entries: KnowledgeEntry[]) => void;
}) {
  function addAnswer() {
    onChange([...entries, { question: "", answer: "" }]);
  }
  function updateAnswer(index: number, changes: Partial<KnowledgeEntry>) {
    onChange(
      entries.map((entry, current) =>
        current === index ? { ...entry, ...changes } : entry,
      ),
    );
  }
  function removeAnswer(index: number) {
    onChange(entries.filter((_, current) => current !== index));
  }
  return (
    <section className="panel form-panel">
      <div className="panel-title">
        <h2>Approved knowledge</h2>
        <button
          type="button"
          onClick={() =>
            onStaffChange([
              ...staff,
              {
                id: `staff-${crypto.randomUUID()}`,
                name: "",
                role: "physiotherapist",
                qualifications: [],
                active: true,
              },
            ])
          }
        >
          + Add staff
        </button>
        <button type="button" onClick={addAnswer}>
          + Add FAQ
        </button>
      </div>
      <p>
        Enter staff roles and qualifications separately. A PhD does not
        establish medical-doctor status. Services, prices and hours stay in
        their existing settings.
      </p>
      <h3>Staff</h3>
      {!staff.length && (
        <p>No structured staff added. Existing FAQs remain available.</p>
      )}
      {staff.map((member) => (
        <StaffEditor
          key={member.id}
          member={member}
          onChange={(changes) =>
            onStaffChange(
              staff.map((current) =>
                current.id === member.id ? { ...current, ...changes } : current,
              ),
            )
          }
          onRemove={() =>
            onStaffChange(staff.filter((current) => current.id !== member.id))
          }
        />
      ))}
      <h3>FAQs and approved information</h3>
      {entries.map((entry, index) => (
        <div className="knowledge" key={index}>
          <label>
            Question
            <input
              required
              value={entry.question}
              onChange={(event) =>
                updateAnswer(index, { question: event.target.value })
              }
            />
          </label>
          <label>
            Approved information
            <textarea
              required
              value={entry.answer}
              onChange={(event) =>
                updateAnswer(index, { answer: event.target.value })
              }
            />
          </label>
          <button type="button" onClick={() => removeAnswer(index)}>
            Remove
          </button>
        </div>
      ))}
    </section>
  );
}
