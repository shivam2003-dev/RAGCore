import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/topbar";

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
        <Sidebar />
        <div className="pl-[248px]">
          <TopBar />
          <main className="mx-auto max-w-[1440px] px-8 py-7">{children}</main>
        </div>
      </body>
    </html>
  );
}
