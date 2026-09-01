import "./globals.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "ReconGrid AI • Autonomous Settlement Reconciliation & Diagnostic Copilot",
  description:
    "Autonomous 4-tier deterministic settlement reconciliation, fee decomposition (MDR 2% + GST 18%), Section 194-O TDS deduction, multi-candidate conflict resolution, and audited Q&A Copilot for Razorpay merchants.",
  keywords: [
    "Reconciliation",
    "Razorpay",
    "Fintech",
    "Bank Statement",
    "MDR Fee",
    "GST ITC",
    "Section 194-O",
    "Settlement Diagnostics",
    "Audit Trail",
  ],
};

export const viewport: Viewport = {
  themeColor: "#060913",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-[#060913] text-slate-100 min-h-screen antialiased selection:bg-blue-600/90 selection:text-white font-sans">
        {children}
      </body>
    </html>
  );
}
