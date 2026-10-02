"use client";

import type { BusinessHours as Hours } from "@/lib/types";
const days = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

export default function BusinessHours({
  hours,
  onChange,
}: {
  hours: Hours[];
  onChange: (hours: Hours[]) => void;
}) {
  function toggleDay(weekday: number, enabled: boolean) {
    onChange(
      enabled
        ? [...hours, { weekday, opens: "09:00", closes: "17:00" }]
        : hours.filter((hour) => hour.weekday !== weekday),
    );
  }
  function changeTime(
    weekday: number,
    field: "opens" | "closes",
    value: string,
  ) {
    onChange(
      hours.map((hour) =>
        hour.weekday === weekday ? { ...hour, [field]: value } : hour,
      ),
    );
  }
  return (
    <section className="panel form-panel">
      <h2>Opening hours</h2>
      <p>Times use the clinic timezone.</p>
      {days.map((day, weekday) => {
        const hour = hours.find((hour) => hour.weekday === weekday);
        return (
          <div className="hours" key={day}>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={Boolean(hour)}
                onChange={(event) => toggleDay(weekday, event.target.checked)}
              />
              {day.slice(0, 3)}
            </label>
            {hour ? (
              <>
                <input
                  aria-label={`${day} opens`}
                  type="time"
                  value={hour.opens.slice(0, 5)}
                  onChange={(event) =>
                    changeTime(weekday, "opens", event.target.value)
                  }
                />
                <span>–</span>
                <input
                  aria-label={`${day} closes`}
                  type="time"
                  value={hour.closes.slice(0, 5)}
                  onChange={(event) =>
                    changeTime(weekday, "closes", event.target.value)
                  }
                />
              </>
            ) : (
              <small>Closed</small>
            )}
          </div>
        );
      })}
    </section>
  );
}
