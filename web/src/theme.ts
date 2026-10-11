// Every color of the web UI (docs/web-ui.md "Decisions"; plan "Global Constraints").
// Orange is for the brand and the main buttons only; never in charts.
export const colors = {
  brand: "#FF6200",
  ink: "#1D2440",
  muted: "#667085",
  surface: "#F7F8FA",
  chart: "#4676BF",
  category: "#D0D5DD",
  riskEmpty: "#E4E7EC",
  good: { bg: "#ECFDF3", fg: "#067647" },
  bad: { bg: "#FEF3F2", fg: "#B42318" },
  neutral: { bg: "#F2F4F7", fg: "#344054" },
  star: "#F5A524",
  starOff: "#E4E7EC",
} as const;

// SPK risk value 1..7, green to red.
export const riskColors = [
  "#12B76A",
  "#66C61C",
  "#A6C612",
  "#F79009",
  "#EF6820",
  "#E04F16",
  "#D92D20",
] as const;
