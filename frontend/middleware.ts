import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const protectedPaths = ["/dashboard", "/issues", "/map", "/engineers", "/settings", "/admin"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const sessionActive = request.cookies.get("session_active")?.value;

  const isProtected = protectedPaths.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );

  if (isProtected && !sessionActive) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|api).*)"],
};
