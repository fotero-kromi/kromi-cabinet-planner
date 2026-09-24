import { createTheme } from "@mantine/core";

// KROMI green (#006C52) at the primary shade, as in the Streamlit app's styling.
export const theme = createTheme({
  primaryColor: "kromi",
  primaryShade: 6,
  colors: {
    kromi: [
      "#e7f5f0", "#cfe9e0", "#a0d3c1", "#6dbca0", "#43a884",
      "#27996f", "#006c52", "#005c46", "#004d3a", "#063b31",
    ],
  },
  fontFamily: "Arial, Helvetica, sans-serif",
  headings: { fontFamily: "Arial, Helvetica, sans-serif" },
  defaultRadius: "sm",
});
