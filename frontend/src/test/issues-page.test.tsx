import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import IssuesPage from "@/app/(authenticated)/issues/page"

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe("IssuesPage", () => {
  it("renders issues list", async () => {
    render(<IssuesPage />, { wrapper })
    await waitFor(() => {
      expect(screen.getByText("Pothole")).toBeInTheDocument()
    })
    expect(screen.getByText("1 total issues")).toBeInTheDocument()
  })

  it("shows report button", async () => {
    render(<IssuesPage />, { wrapper })
    await waitFor(() => {
      expect(screen.getByText("Report Issue")).toBeInTheDocument()
    })
  })
})
