import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Sidebar } from "@/components/layout/sidebar"

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/store/auth", () => ({
  useAuthStore: () => vi.fn(),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe("Sidebar", () => {
  it("renders navigation links", () => {
    render(<Sidebar />, { wrapper })
    expect(screen.getByText("CivicPulse")).toBeInTheDocument()
    expect(screen.getByText("Dashboard")).toBeInTheDocument()
    expect(screen.getByText("Issues")).toBeInTheDocument()
    expect(screen.getByText("Map")).toBeInTheDocument()
    expect(screen.getByText("Engineers")).toBeInTheDocument()
  })

  it("highlights active route", () => {
    render(<Sidebar />, { wrapper })
    const dashboardLink = screen.getByText("Dashboard").closest("a")
    expect(dashboardLink).toHaveClass("bg-primary/[0.08]")
    expect(screen.getByText("Sign Out")).toBeInTheDocument()
  })
})
