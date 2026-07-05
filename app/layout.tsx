import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthShell } from "@/components/auth-shell";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kimbal Knowledge Hub",
  description: "Unified knowledge. Smarter answers. Better decisions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="min-h-full font-sans">
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
