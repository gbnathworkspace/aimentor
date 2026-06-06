import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { type NextRequest, NextResponse } from 'next/server';

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};

const isPublicRoute = createRouteMatcher(['/sign-in(.*)', '/sign-up(.*)']);

// When DISABLE_AUTH=true, export a plain passthrough — Clerk never runs.
// When DISABLE_AUTH=false/unset, protect all non-public routes via Clerk.
export default process.env.DISABLE_AUTH === 'true'
  ? (_req: NextRequest) => NextResponse.next()
  : clerkMiddleware(async (auth, request) => {
      if (!isPublicRoute(request)) await auth.protect();
    });
