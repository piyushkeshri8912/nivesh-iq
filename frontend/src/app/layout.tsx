import type { Metadata } from "next";
import { Archivo, Space_Grotesk, Fira_Code } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/layout/app-shell";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const firaCode = Fira_Code({
  variable: "--font-fira-code",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "NiveshIQ — AI Portfolio Intelligence",
  description: "Advanced explainable AI portfolio reviews and analysis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${spaceGrotesk.variable} ${firaCode.variable} h-full antialiased dark`}
    >
      <body className="min-h-full bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-50">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
