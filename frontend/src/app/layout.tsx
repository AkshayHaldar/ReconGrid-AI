import "./globals.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "ReconGrid • Settlement Reconciliation Console",
  description:
    "Deterministic settlement reconciliation, fee decomposition (MDR 2% + GST 18%), Section 194-O TDS deduction, multi-candidate conflict resolution, and audited ledger verification for Razorpay merchants.",
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
  themeColor: "#090a0f",
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
      <body className="bg-[#090a0f] text-neutral-100 min-h-screen antialiased selection:bg-neutral-800 selection:text-white font-sans">
        {children}
      </body>
    </html>
  );
}
