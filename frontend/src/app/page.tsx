"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { NumberTicker } from "@/components/ui/number-ticker";
import {
  ArrowRight,
  BarChart3,
  Camera,
  CheckCircle2,
  Landmark,
  Map,
  MapPin,
  Plus,
  Quote,
  ShieldCheck,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";

const features = [
  {
    icon: Camera,
    title: "Photo-Driven Reports",
    desc: "Field teams capture an issue once — the platform reads the image, GPS, and description together.",
    accent: "from-sky-500 to-blue-600",
  },
  {
    icon: Sparkles,
    title: "Intelligent Classification",
    desc: "Every report is categorized with confidence scoring, so nothing falls through the cracks.",
    accent: "from-indigo-500 to-violet-600",
  },
  {
    icon: Wrench,
    title: "Automatic Routing",
    desc: "Issues are matched to the right engineer and ward the moment they enter the system.",
    accent: "from-amber-500 to-orange-600",
  },
  {
    icon: Map,
    title: "City-Wide Heatmap",
    desc: "See problem clusters across every ward on an interactive map with severity markers.",
    accent: "from-emerald-500 to-teal-600",
  },
  {
    icon: BarChart3,
    title: "Live Analytics",
    desc: "Resolution rates, backlog, and trends update in real time as reports flow in.",
    accent: "from-fuchsia-500 to-pink-600",
  },
  {
    icon: ShieldCheck,
    title: "Secure By Role",
    desc: "Admins, engineers, and field teams each get a workspace tuned to their job.",
    accent: "from-violet-500 to-purple-600",
  },
];

const marqueeItems = [
  "Pothole Detection",
  "Streetlight Monitoring",
  "Waste Management",
  "Waterlogging Alerts",
  "Road Health",
  "Drainage & Sewage",
  "Public Safety",
  "Community Feedback",
];

const metrics = [
  { value: 38, suffix: "+", label: "Issues resolved monthly" },
  { value: 10, suffix: "", label: "Wards connected" },
  { value: 7, suffix: "", label: "Issue categories" },
  { value: 2, prefix: "<", suffix: "s", label: "Average AI analysis" },
];

const steps = [
  {
    icon: Camera,
    step: "01",
    title: "Report",
    desc: "A field worker snaps a photo and pins the location. GPS from the image is captured automatically.",
  },
  {
    icon: Sparkles,
    step: "02",
    title: "Classify",
    desc: "The platform categorizes the issue, scores severity, and flags anything that needs human review.",
  },
  {
    icon: CheckCircle2,
    step: "03",
    title: "Resolve",
    desc: "Engineers are routed automatically and updates stream live until the issue is closed and verified.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-border/60 bg-background/75 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-glow-primary">
              <Landmark className="h-5 w-5" />
            </div>
            <span className="text-lg font-semibold tracking-tight">CivicPulse</span>
          </Link>
          <div className="hidden items-center gap-8 text-sm font-medium text-muted-foreground md:flex">
            <Link href="#platform" className="transition-colors hover:text-foreground">
              Platform
            </Link>
            <Link href="#features" className="transition-colors hover:text-foreground">
              Features
            </Link>
            <Link href="#how" className="transition-colors hover:text-foreground">
              How it works
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login">
              <Button variant="ghost" size="sm">
                Sign In
              </Button>
            </Link>
            <Link href="/register">
              <Button size="sm" className="gap-1.5">
                Get Started
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.07] via-transparent to-background" />
          <div aria-hidden className="absolute inset-0 bg-dots opacity-60" />
          <div
            aria-hidden
            className="absolute -left-40 top-[-20%] h-[30rem] w-[30rem] animate-aurora rounded-full bg-indigo-500/20 blur-3xl"
          />
          <div
            aria-hidden
            className="absolute right-[-10%] top-[-5%] h-[26rem] w-[26rem] animate-aurora-slow rounded-full bg-violet-500/20 blur-3xl"
          />
          <div
            aria-hidden
            className="absolute bottom-[-30%] left-1/3 h-[28rem] w-[28rem] rounded-full bg-sky-500/10 blur-3xl"
          />
        </div>

        <div className="relative mx-auto grid max-w-6xl gap-14 px-6 pb-20 pt-16 md:pt-24 lg:grid-cols-2 lg:items-center">
          <div>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-card/70 px-3.5 py-1.5 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                Live across Vadodara Municipal
              </div>
              <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-tight md:text-[3.4rem]">
                Smarter cities start with{" "}
                <span className="text-gradient">smarter issue tracking</span>
              </h1>
              <p className="mt-5 max-w-lg text-lg leading-relaxed text-muted-foreground">
                CivicPulse unifies reporting, AI classification, routing, and
                resolution in one enterprise-grade command center for the city.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-4">
                <Link href="/register">
                  <Button size="lg" className="gap-2">
                    Start Reporting
                    <Plus className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/login">
                  <Button size="lg" variant="outline" className="gap-2">
                    <Map className="h-4 w-4" />
                    Explore the dashboard
                  </Button>
                </Link>
              </div>
            </motion.div>
          </div>

          {/* Product preview */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15 }}
            className="relative"
          >
            <div className="relative rounded-2xl border border-border/80 bg-card p-5 shadow-[0_20px_60px_-24px_rgb(0_0_0/0.25)]">
              <div className="mb-4 flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
                <span className="ml-3 text-xs font-medium text-muted-foreground">
                  command-center.civicpulse.dev
                </span>
              </div>

              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">Operations Overview</p>
                  <p className="text-xs text-muted-foreground">This week across 10 wards</p>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Live
                </span>
              </div>

              <div className="mb-5 grid grid-cols-3 gap-3">
                {[
                  { label: "Reports", value: "38", tone: "text-foreground" },
                  { label: "In progress", value: "12", tone: "text-amber-600 dark:text-amber-400" },
                  { label: "Resolved", value: "9", tone: "text-emerald-600 dark:text-emerald-400" },
                ].map((k) => (
                  <div key={k.label} className="rounded-xl border border-border/70 bg-background/60 p-3">
                    <p className={`text-xl font-semibold tracking-tight ${k.tone}`}>{k.value}</p>
                    <p className="text-[11px] text-muted-foreground">{k.label}</p>
                  </div>
                ))}
              </div>

              <div className="mb-5 flex h-24 items-end gap-2">
                {[42, 68, 38, 82, 55, 90, 64, 48, 76, 60].map((h, i) => (
                  <div key={i} className="flex-1 rounded-t-md bg-gradient-to-t from-indigo-600 to-violet-400 opacity-70"
                    style={{ height: `${h}%` }} />
                ))}
              </div>

              <div className="space-y-2">
                {[
                  { t: "Pothole", w: "Ward 4", s: "Resolved", c: "bg-emerald-500" },
                  { t: "Broken streetlight", w: "Ward 7", s: "In progress", c: "bg-amber-500" },
                  { t: "Waterlogging", w: "Ward 2", s: "Reported", c: "bg-sky-500" },
                ].map((r) => (
                  <div key={r.t} className="flex items-center justify-between rounded-lg border border-border/60 bg-background/50 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted text-muted-foreground">
                        <MapPin className="h-3 w-3" />
                      </span>
                      <span className="text-xs font-medium">{r.t}</span>
                      <span className="text-[11px] text-muted-foreground">{r.w}</span>
                    </div>
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                      <span className={`h-1.5 w-1.5 rounded-full ${r.c}`} />
                      {r.s}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Floating badge */}
            <div className="absolute -right-3 -top-4 animate-float rounded-xl border border-border/70 bg-card px-3.5 py-2.5 shadow-lift sm:-right-6">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold">AI classified</p>
                  <p className="text-[11px] text-muted-foreground">Confidence scored</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Marquee */}
      <section className="border-y border-border/60 bg-card/50 py-5">
        <div className="mask-fade-x overflow-hidden">
          <div className="flex w-max animate-marquee items-center gap-12 pr-12">
            {[...marqueeItems, ...marqueeItems].map((item, i) => (
              <span key={i} className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Zap className="h-3.5 w-3.5 text-primary" />
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-6 py-20 md:py-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mx-auto mb-14 max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            Platform
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
            Everything the city needs to{" "}
            <span className="text-gradient">respond faster</span>
          </h2>
          <p className="mt-4 text-muted-foreground">
            From a photo taken on the street to a resolved work order — every step
            is designed to be effortless.
          </p>
        </motion.div>

        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: (i % 3) * 0.08 }}
              className="group relative overflow-hidden rounded-2xl border border-border/80 bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-primary/30 hover:shadow-lift"
            >
              <div
                aria-hidden
                className="absolute -right-16 -top-16 h-40 w-40 rounded-full bg-gradient-to-br from-indigo-500/10 to-violet-500/10 blur-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
              />
              <div
                className={`mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-sm ${f.accent}`}
              >
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold tracking-tight">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Metrics */}
      <section className="border-y border-border/60 bg-card/50">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-8 px-6 py-14 md:grid-cols-4">
          {metrics.map((m) => (
            <div key={m.label} className="text-center">
              <p className="text-3xl font-semibold tracking-tight md:text-4xl">
                {m.prefix && <span className="text-muted-foreground">{m.prefix}</span>}
                <NumberTicker value={m.value} />
                {m.suffix}
              </p>
              <p className="mt-1.5 text-sm text-muted-foreground">{m.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-6xl px-6 py-20 md:py-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mx-auto mb-14 max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            How it works
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
            From street to resolution in three steps
          </h2>
        </motion.div>

        <div className="grid gap-5 md:grid-cols-3">
          {steps.map((s, i) => (
            <motion.div
              key={s.step}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: i * 0.1 }}
              className="relative rounded-2xl border border-border/80 bg-card p-6"
            >
              <span className="absolute right-5 top-5 text-3xl font-semibold text-muted-foreground/20">
                {s.step}
              </span>
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
                <s.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold tracking-tight">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Testimonial */}
      <section className="mx-auto max-w-4xl px-6 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-br from-indigo-950 via-blue-950 to-violet-950 p-8 text-white md:p-12"
        >
          <div aria-hidden className="absolute inset-0 bg-grid-white opacity-50" />
          <div aria-hidden className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-indigo-500/30 blur-3xl" />
          <div className="relative">
            <Quote className="h-8 w-8 text-indigo-300" />
            <p className="mt-5 text-xl font-medium leading-relaxed md:text-2xl">
              &ldquo;Designed to reduce average complaint-to-resolution time from
              days to hours through AI-powered triage and automated routing.&rdquo;
            </p>
          </div>
        </motion.div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-gradient-to-br from-indigo-600 via-indigo-500 to-violet-600 px-6 py-14 text-center text-white md:px-12 md:py-16">
          <div aria-hidden className="absolute inset-0 bg-grid-white opacity-40" />
          <div
            aria-hidden
            className="absolute -left-24 -top-24 h-64 w-64 animate-aurora rounded-full bg-white/15 blur-3xl"
          />
          <div
            aria-hidden
            className="absolute -bottom-24 -right-24 h-64 w-64 animate-aurora-slow rounded-full bg-violet-300/20 blur-3xl"
          />
          <div className="relative">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              Ready to transform civic monitoring?
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-indigo-100">
              Join the team keeping Vadodara&apos;s streets safe, clean, and moving.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <Link href="/register">
                <Button size="lg" className="bg-white text-indigo-700 shadow-lg hover:bg-indigo-50">
                  Create an account
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Link href="/login">
                <Button
                  size="lg"
                  variant="outline"
                  className="border-white/30 bg-white/10 text-white backdrop-blur hover:bg-white/20 hover:text-white"
                >
                  Sign in
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white">
              <Landmark className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight">CivicPulse</span>
          </div>
          <p className="text-sm text-muted-foreground">
            AI Urban Issue Intelligence · Vadodara Municipal
          </p>
          <p className="text-xs text-muted-foreground/70">
            © {new Date().getFullYear()} CivicPulse
          </p>
        </div>
      </footer>
    </div>
  );
}
