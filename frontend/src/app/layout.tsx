import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ReconGrid AI — Settlement Reconciliation & Diagnostic Engine",
  description:
    "Autonomous deterministic settlement reconciliation and discrepancy diagnostic engine for Razorpay merchants (Track 04: AI Finance Controller)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#070b12] text-slate-100 min-h-screen antialiased selection:bg-blue-600 selection:text-white">
        {children}
      </body>
    </html>
  );
}
