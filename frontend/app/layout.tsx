import type { Metadata } from "next";
import localFont from "next/font/local";
import Shell from "@/components/Shell";
import { AppProvider } from "@/lib/app-context";
import "./globals.css";

const urbanist = localFont({ src: "./fonts/Urbanist.ttf", variable: "--font-urbanist", weight: "100 900", display: "block" });

export const metadata: Metadata = { title: "OfficeFlow", description: "Offline office automation" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={urbanist.variable} suppressHydrationWarning>
      <body>
        <AppProvider>
          <Shell>{children}</Shell>
        </AppProvider>
      </body>
    </html>
  );
}
