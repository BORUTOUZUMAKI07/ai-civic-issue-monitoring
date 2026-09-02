"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/api";

export function OAuthButtons() {
  const [providers, setProviders] = useState<{ google: boolean; github: boolean } | null>(null);

  useEffect(() => {
    let active = true;
    auth
      .oauthProviders()
      .then((p) => {
        if (active) setProviders(p);
      })
      .catch(() => {
        if (active) setProviders({ google: false, github: false });
      });
    return () => {
      active = false;
    };
  }, []);

  function handleOAuth(provider: "google" | "github") {
    // Preserve any ?redirect= so the post-login destination carries through,
    // then do a full-page navigation: the OAuth callback is a top-level redirect
    // that sets auth cookies on the frontend domain in the same tab.
    const redirect = new URLSearchParams(window.location.search).get("redirect") || "/dashboard";
    window.location.href = auth.oauthAuthorizeUrl(provider, redirect);
  }

  if (providers && !providers.google && !providers.github) {
    return null;
  }

  return (
    <div className="space-y-3">
      {(!providers || providers.google) && (
        <Button
          type="button"
          variant="outline"
          className="h-10 w-full"
          onClick={() => handleOAuth("google")}
        >
          <GoogleIcon className="mr-2 h-4 w-4" />
          Continue with Google
        </Button>
      )}
      {(!providers || providers.github) && (
        <Button
          type="button"
          variant="outline"
          className="h-10 w-full"
          onClick={() => handleOAuth("github")}
        >
          <GithubIcon className="mr-2 h-4 w-4" />
          Continue with GitHub
        </Button>
      )}

      <div className="flex items-center gap-3 py-1">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs uppercase tracking-wide text-muted-foreground">or</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden fill="currentColor">
      <path d="M23.5 12.27c0-.79-.07-1.55-.2-2.27H12v4.51h6.46a5.57 5.57 0 0 1-2.4 3.6v3h3.9c2.28-2.1 3.54-5.19 3.54-8.84Z" fill="#4285F4" />
      <path d="M12 24c3.24 0 5.96-1.08 7.94-2.88l-3.9-3a8.64 8.64 0 0 1-4.04 1.06c-2.1 0-3.87-.71-5.16-1.92l-3.7 2.87A12 12 0 0 0 12 24Z" fill="#34A853" />
      <path d="M6.84 11.26a7.22 7.22 0 0 1 0-1.71V6.68H3.14a12 12 0 0 0 0 10.64l3.7-2.87Z" fill="#FBBC05" />
      <path d="M12 4.82c1.76 0 3.33.6 4.58 1.8l3.43-3.43A11.96 11.96 0 0 0 12 0 11.99 11.99 0 0 0 3.14 6.68l3.7 2.87C8.13 5.53 9.9 4.82 12 4.82Z" fill="#EA4335" />
    </svg>
  );
}

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden fill="currentColor">
      <path d="M12 .5a11.5 11.5 0 0 0-3.63 22.41c.58.1.79-.25.79-.56v-2.14c-3.22.7-3.9-1.55-3.9-1.55-.53-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.71.08-.71 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.23-1.28-5.23-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.25 5.67.41.35.78 1.05.78 2.12v3.15c0 .31.2.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}