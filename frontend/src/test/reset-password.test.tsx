import { afterEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import ResetPasswordPage from "@/app/(auth)/reset-password/page"

const pushMock = vi.hoisted(() => vi.fn())

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("token=valid-token"),
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  pushMock.mockClear()
})

describe("ResetPasswordPage", () => {
  it("keeps the success confirmation visible instead of bouncing to /login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Password reset" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)

    render(<ResetPasswordPage />)
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "secret123" } })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "secret123" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Update password" }))

    await waitFor(() => expect(screen.getByText("Password updated")).toBeInTheDocument())
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login")
    // The old code pushed /login in the same tick, so nobody ever saw the
    // confirmation and the link on it was dead code.
    expect(pushMock).not.toHaveBeenCalled()
  })
})
