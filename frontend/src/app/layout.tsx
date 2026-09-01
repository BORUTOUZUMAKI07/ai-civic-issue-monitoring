import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { Providers } from "@/lib/providers";
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
  title: "CivicPulse - AI Urban Issue Intelligence",
  description: "AI-powered civic issue monitoring, classification, and resolution tracking platform",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "CivicPulse - AI Urban Issue Intelligence",
    description: "AI-powered civic issue monitoring and resolution tracking",
    type: "website",
  },
};

async function getNewRelicBrowserHeader(): Promise<string | null> {
  if (!process.env.NEW_RELIC_LICENSE_KEY) {
    return null;
  }
  try {
    const { default: newrelic } = await import("newrelic");
    const agent = newrelic?.agent;
    if (!agent || agent.collector?.isConnected?.() === false) {
      await new Promise((resolve) => {
        const done = () => resolve(undefined);
        const timer = setTimeout(done, 8000);
        agent?.once("connected", () => {
          clearTimeout(timer);
          resolve(undefined);
        });
      });
    }
    if (typeof newrelic.getBrowserTimingHeader !== "function") {
      return null;
    }
    return String(
      newrelic.getBrowserTimingHeader({
        hasToRemoveScriptWrapper: true,
        allowTransactionlessInjection: true,
      })
    );
  } catch {
    return null;
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const nrHeader = await getNewRelicBrowserHeader();

  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-scroll-behavior="smooth"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {nrHeader ? (
          <Script
            id="nr-browser-agent"
            strategy="beforeInteractive"
            dangerouslySetInnerHTML={{ __html: nrHeader }}
          />
        ) : null}
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
