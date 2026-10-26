export const theme = {
  // Change these semantic values here AND the matching CSS variables in globals.css.
  colors: {
    brand: "#071A2D",
    brandStrong: "#04111F",
    onBrand: "#FFFFFF",
    onAccent: "#04111F",
    accent: "#00A7C4",
    accentSoft: "#E7F8FB",
    background: "#F7F9FB",
    surface: "#FFFFFF",
    surfaceSubtle: "#F1F4F7",
    border: "#D6DEE6",
    borderStrong: "#AAB8C5",
    text: "#102033",
    textMuted: "#627286",
    healthy: "#18794E",
    warning: "#A15C00",
    critical: "#B42318",
    offline: "#697586",
    info: "#1565A7",
    navText: "#DCE7EF",
  },
  radius: {
    xs: 2,
    sm: 4,
    md: 6,
  },
  sidebar: {
    expanded: 244,
    collapsed: 64,
  },
} as const;
