import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stackpoint — Loan Records",
  description: "Structured borrower records extracted from loan documents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="mx-auto max-w-6xl px-6 py-8">
          <header className="mb-12 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-accent-500 to-accent-600 text-sm font-semibold">
                S
              </span>
              <span className="font-display text-xl tracking-tight">
                Stackpoint
              </span>
            </Link>
            <nav className="flex items-center gap-6 text-sm text-navy-200">
              <Link href="/" className="hover:text-white">Borrowers</Link>
              <Link href="/flags" className="hover:text-white">Flags</Link>
            </nav>
          </header>
          {children}
          <footer className="mt-24 border-t border-white/5 pt-6 text-xs text-navy-300">
            Take-home demo — extraction pipeline in <code>apps/extractor</code>, UI in <code>apps/web</code>.
          </footer>
        </div>
      </body>
    </html>
  );
}
