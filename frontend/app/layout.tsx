import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { Providers } from "@/components/providers";
import { getTheme, themeToStyleRecord, DEFAULT_THEME_ID } from "@/lib/themes";

const inter = Inter({
  variable: "--font-prose",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ANVAYA",
  description: "Self-correcting cyber defense dashboard",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const savedThemeId = cookieStore.get("anvaya-theme")?.value;
  const initialThemeId = getTheme(savedThemeId ?? "")?.id ?? DEFAULT_THEME_ID;
  const theme = getTheme(initialThemeId)!;
  const initialStyle = themeToStyleRecord(theme);

  return (
    <html
      lang="en"
      data-theme={initialThemeId}
      style={initialStyle}
      className="dark"
    >
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}>
        <Providers initialThemeId={initialThemeId}>{children}</Providers>
      </body>
    </html>
  );
}
