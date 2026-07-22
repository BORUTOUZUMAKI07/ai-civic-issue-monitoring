import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import DashboardPage from "@/app/(authenticated)/dashboard/page"

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe("DashboardPage", () => {
  it("renders dashboard stats", async () => {
    render(<DashboardPage />, { wrapper })
    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument()
    })
  })
})
