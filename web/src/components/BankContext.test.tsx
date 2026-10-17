// W25 / W46: the other banks' rates are not shown (the user, 2026-10-17); the rate helpers stay.
import { render, screen } from "@testing-library/react";
import type { OptionView } from "../api/types";
import { sample } from "../test/samples";
import { fmtPoints, fmtRate } from "./BankContext";
import { FundCard } from "./FundCard";

const ID = "time_deposit:ing_e_vadeli";
const option = (): OptionView => sample("run_p01_ready").options[ID];

test("W46: the fund card of the time deposit has no other-banks block", () => {
  expect(option().bank_context?.rows).toHaveLength(3); // the API still sends the rows
  render(<FundCard option={option()} onEvidence={vi.fn()} />);
  expect(screen.queryByTestId("bank-context")).toBeNull();
  expect(screen.queryByText(/Diğer bankalar/)).toBeNull();
  expect(screen.queryByText(/İş Bankası/)).toBeNull();
  expect(screen.queryByText(/37,00/)).toBeNull();
});

test("the rate helpers: Turkish percent and signed points with the Turkish minus sign", () => {
  expect(fmtRate(34.5)).toBe("%34,50");
  expect(fmtPoints(2.5)).toBe("+2,50");
  expect(fmtPoints(-3.5)).toBe("−3,50");
  expect(fmtPoints(0)).toBe("0,00");
});
