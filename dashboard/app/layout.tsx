import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LO206 Dyno Dashboard",
  description:
    "Live telemetry, run history, and CSV export for the LO206 dynamometer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
    </html>
  );
}
