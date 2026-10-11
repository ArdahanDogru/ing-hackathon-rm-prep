import { colors } from "../theme";

/** 1..5 stars inside the category (Morningstar-style split, computed by the API). */
export function Stars({ count }: { count: number }) {
  return (
    <span role="img" aria-label={`5 üzerinden ${count} yıldız`} className="text-[15px] leading-none tracking-[1px]">
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          data-testid={i < count ? "star-on" : "star-off"}
          aria-hidden="true"
          style={{ color: i < count ? colors.star : colors.starOff }}
        >
          ★
        </span>
      ))}
    </span>
  );
}
