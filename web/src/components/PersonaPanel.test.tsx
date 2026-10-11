import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { sample } from "../test/samples";
import { PersonaPanel } from "./PersonaPanel";

test("all persona fields; Uygula sends the edited persona", async () => {
  const p = sample("personas")[0];
  const onApply = vi.fn();
  render(<PersonaPanel persona={p} onApply={onApply} onClose={() => {}} />);
  for (const label of ["yaş", "risk profili", "öncelikler", "açık kısıtlar", "dosyadaki not"]) {
    expect(screen.getByLabelText(new RegExp(`^${label}`))).toBeInTheDocument();
  }
  const age = screen.getByLabelText("yaş");
  await userEvent.clear(age);
  await userEvent.type(age, "45");
  const prios = screen.getByLabelText(/^öncelikler/);
  await userEvent.clear(prios);
  await userEvent.type(prios, "düzenli gelir{enter}  {enter}büyüme");
  await userEvent.click(screen.getByRole("button", { name: "Uygula" }));
  const edited = onApply.mock.calls[0][0];
  expect(edited.yas).toBe(45);
  expect(edited.oncelikler).toEqual(["düzenli gelir", "büyüme"]);
  expect(edited.persona_id).toBe(p.persona_id);
});

test("Vazgeç closes without a run", async () => {
  const onApply = vi.fn();
  const onClose = vi.fn();
  render(<PersonaPanel persona={sample("personas")[0]} onApply={onApply} onClose={onClose} />);
  await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
  expect(onClose).toHaveBeenCalled();
  expect(onApply).not.toHaveBeenCalled();
});
