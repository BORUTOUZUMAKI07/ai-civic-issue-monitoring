import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { Sidebar } from "@/components/layout/sidebar"

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/store/auth", () => ({
  useAuthStore: () => vi.fn(),
}))

describe("Sidebar", () => {
  it("renders navigation links", () => {
    render(<Sidebar />)
    expect(screen.getByText("CivicPulse")).toBeInTheDocument()
    expect(screen.getByText("Dashboard")).toBeInTheDocument()
    expect(screen.getByText("Issues")).toBeInTheDocument()
    expect(screen.getByText("Map")).toBeInTheDocument()
    expect(screen.getByText("Engineers")).toBeInTheDocument()
  })

  it("highlights active route", () => {
    render(<Sidebar />)
    const dashboardLink = screen.getByText("Dashboard").closest("a")
    expect(dashboardLink).toHaveClass("bg-primary")
  })
})
