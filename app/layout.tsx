import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Target Scout",
  description: "Evidence-ranked drug targets with a human checkpoint",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <nav className="flex items-center gap-4 border-b border-zinc-200 px-6 py-3 text-sm dark:border-zinc-800">
          <span className="font-semibold">Target Scout</span>
          <Link href="/" className="hover:underline">Scout</Link>
          <Link href="/screening" className="hover:underline">Screening</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
