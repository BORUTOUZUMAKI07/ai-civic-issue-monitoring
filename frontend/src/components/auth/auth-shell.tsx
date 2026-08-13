"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Activity, Landmark, ShieldCheck, Zap } from "lucide-react";

const highlights = [
  {
    icon: Zap,
    title: "AI-powered classification",
    desc: "Every field report is analyzed, categorized, and routed automatically.",
  },
  {
    icon: Activity,
    title: "Live city-wide tracking",
    desc: "Watch issues move from report to resolution in real time.",
  },
  {
    icon: ShieldCheck,
    title: "Role-based workspaces",
    desc: "Secure access for admins, engineers, and field teams.",
  },
];

const stats = [
  { value: "38+", label: "Issues tracked" },
  { value: "10", label: "Wards covered" },
  { value: "<2s", label: "AI analysis" },
];

export function AuthShell({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* Showcase panel */}
      <div className="relative hidden w-1/2 overflow-hidden border-r border-white/5 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-950 via-blue-950 to-violet-950" />
        <div aria-hidden className="absolute inset-0 bg-grid-white opacity-60" />
        <div
          aria-hidden
          className="absolute -left-32 top-[-10%] h-[28rem] w-[28rem] animate-aurora rounded-full bg-indigo-600/40 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute -right-24 bottom-[-12%] h-[26rem] w-[26rem] animate-aurora-slow rounded-full bg-violet-600/40 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute left-1/3 top-1/3 h-64 w-64 rounded-full bg-sky-500/20 blur-3xl"
        />
        <div aria-hidden className="absolute inset-0 bg-noise opacity-[0.15]" />

        <div className="relative z-10 p-12">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 to-violet-500 shadow-glow-primary">
              <Landmark className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-lg font-semibold leading-tight text-white">CivicPulse</p>
              <p className="text-xs text-indigo-200/80">Vadodara Municipal</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 p-12">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          >
            <h2 className="max-w-md text-3xl font-semibold leading-tight tracking-tight text-white">
              The operating system for{" "}
              <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-sky-300 bg-clip-text text-transparent">
                modern city services
              </span>
            </h2>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-indigo-200/85">
              One platform to report, classify, and resolve civic issues across the
              city — powered by AI.
            </p>

            <div className="mt-8 space-y-4">
              {highlights.map((h) => (
                <div key={h.title} className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-inset ring-white/15">
                    <h.icon className="h-4 w-4 text-indigo-200" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white">{h.title}</p>
                    <p className="text-xs leading-relaxed text-indigo-200/75">{h.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        <div className="relative z-10 border-t border-white/10 bg-white/[0.04] p-6 backdrop-blur-sm">
          <div className="flex items-center gap-8">
            {stats.map((s) => (
              <div key={s.label}>
                <p className="text-xl font-semibold text-white">{s.value}</p>
                <p className="text-xs text-indigo-200/75">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Form panel */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-10 sm:px-6">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 lg:hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/[0.08] via-transparent to-violet-500/[0.08]" />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
          className="relative w-full max-w-sm"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}
