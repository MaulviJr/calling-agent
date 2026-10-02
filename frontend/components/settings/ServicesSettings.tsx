"use client";

import type { Service } from "@/lib/types";

export default function ServicesSettings({
  services,
  onChange,
}: {
  services: Service[];
  onChange: (services: Service[]) => void;
}) {
  function addService() {
    onChange([
      ...services,
      {
        id: `service-${crypto.randomUUID().slice(0, 6)}`,
        name: "",
        duration: 30,
        price: "",
        active: true,
      },
    ]);
  }
  function updateService(id: string, changes: Partial<Service>) {
    onChange(
      services.map((service) =>
        service.id === id ? { ...service, ...changes } : service,
      ),
    );
  }
  return (
    <section className="panel form-panel">
      <div className="panel-title">
        <h2>Services</h2>
        <button type="button" onClick={addService}>
          + Add service
        </button>
      </div>
      {!services.length && <p>Add a service before accepting bookings.</p>}
      {services.map((service) => (
        <div className="service" key={service.id}>
          <label>
            Name
            <input
              required
              value={service.name}
              onChange={(event) =>
                updateService(service.id, { name: event.target.value })
              }
            />
          </label>
          <label>
            Duration (minutes)
            <input
              type="number"
              min="5"
              max="240"
              value={service.duration}
              onChange={(event) =>
                updateService(service.id, {
                  duration: Number(event.target.value),
                })
              }
            />
          </label>
          <label>
            Approved price
            <input
              value={service.price}
              onChange={(event) =>
                updateService(service.id, { price: event.target.value })
              }
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={service.active}
              onChange={(event) =>
                updateService(service.id, { active: event.target.checked })
              }
            />
            Active
          </label>
        </div>
      ))}
    </section>
  );
}
