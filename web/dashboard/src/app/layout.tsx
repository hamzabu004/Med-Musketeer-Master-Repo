import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

// Product typography.
// Replace this font import + CSS variable to switch the application typeface globally.
const productFont = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-product",
});

export const metadata: Metadata = {
  title: "MedMusketeer",
  description: "MedMusketeer clinical monitoring",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={productFont.variable}>{children}</body>
    </html>
  );
}
