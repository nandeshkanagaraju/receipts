/** SDD §22's tokens, and nothing else. A colour that is not in the table is
 *  not available to a component, which is how "everything else stays quiet"
 *  survives contact with a deadline. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#16233A",
        surface: "#F6F7F9",
        panel: "#FFFFFF",
        rule: "#D9DEE5",
        verified: "#1E7B4F",
        clarify: "#2E5AAC",
        unverified: "#A86A12",
        denied: "#B42318",
        abstain: "#5C6573",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", '"Noto Sans Tamil"', '"Noto Sans Devanagari"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
