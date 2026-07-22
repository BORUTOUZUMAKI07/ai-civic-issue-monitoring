"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Camera, Map, Brain, BarChart3, Zap, Shield } from "lucide-react";

const features = [
  { icon: Camera, title: "AI Image Classification", desc: "Upload a photo and our ML model instantly classifies the civic issue with severity scoring." },
  { icon: Map, title: "Real-time Heatmap", desc: "Interactive map showing all reported issues across Vadodara with severity-based markers." },
  { icon: Brain, title: "LangGraph Agent Pipeline", desc: "Multi-agent system handles classification, routing, engineer matching, and analytics." },
  { icon: BarChart3, title: "Analytics Dashboard", desc: "Live charts showing issue trends, ward-wise distribution, and resolution metrics." },
  { icon: Zap, title: "WebSocket Live Updates", desc: "Real-time notifications when new issues are reported or status changes." },
  { icon: Shield, title: "Role-Based Access", desc: "Admin, engineer, field worker, and viewer roles with granular permissions." },
];

const stats = [
  { value: "7", label: "Issue Categories" },
  { value: "10", label: "Wards Covered" },
  { value: "5", label: "ML Agents" },
  { value: "<2s", label: "Classification Time" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <Zap className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="text-lg font-bold">CivicPulse</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login"><Button variant="ghost" size="sm">Sign In</Button></Link>
            <Link href="/register"><Button size="sm">Get Started</Button></Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-primary/10" />
        <div className="max-w-6xl mx-auto px-6 py-24 md:py-32 relative">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-border/50 px-4 py-1.5 text-xs font-medium text-muted-foreground mb-6">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
              AI-Powered Civic Intelligence Platform
            </div>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight">
              Smarter Cities Start with <span className="text-primary">Smarter Issue Tracking</span>
            </h1>
            <p className="mt-6 text-lg text-muted-foreground max-w-2xl leading-relaxed">
              CivicPulse uses machine learning to classify, route, and track civic infrastructure issues.
              Report problems with a photo, get instant AI analysis, and monitor resolution in real-time.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <Link href="/register">
                <Button size="lg" className="gap-2">
                  Start Reporting Issues
                  <Zap className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/login">
                <Button size="lg" variant="outline">View Dashboard</Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border/50 bg-muted/30">
        <div className="max-w-6xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-3xl font-bold">{s.value}</div>
              <div className="text-sm text-muted-foreground mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">Built for Real Municipal Workflows</h2>
          <p className="mt-3 text-muted-foreground max-w-xl mx-auto">
            From citizen report to engineer dispatch — every step is automated and intelligent.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f) => (
            <Card key={f.title} className="border-border/50 hover:border-primary/30 transition-colors">
              <CardContent className="p-6">
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <f.icon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{f.desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Tech Stack */}
      <section className="border-t border-border/50 bg-muted/30">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-2xl font-bold text-center mb-8">Technology Stack</h2>
          <div className="flex flex-wrap justify-center gap-3">
            {["FastAPI", "LangGraph", "pgvector", "Next.js", "Recharts", "Leaflet", "PostgreSQL", "Redis", "MongoDB", "WebSockets", "HuggingFace", "Groq LLM"].map((t) => (
              <span key={t} className="px-4 py-2 rounded-lg border border-border/50 bg-background text-sm font-medium">
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-6 py-20 text-center">
        <h2 className="text-3xl font-bold">Ready to Transform Civic Monitoring?</h2>
        <p className="mt-3 text-muted-foreground mb-8">Open source. ML-powered. Built for Vadodara Municipal Corporation.</p>
        <Link href="/register">
          <Button size="lg">Create Free Account</Button>
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 py-8 text-center text-sm text-muted-foreground">
        CivicPulse &mdash; AI Urban Issue Intelligence Platform
      </footer>
    </div>
  );
}
