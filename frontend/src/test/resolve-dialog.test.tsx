import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"

const { mutateAsync, toastError, toastSuccess } = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock("@/queries/index", () => ({
  useResolveIssueMutation: () => ({ mutateAsync, isPending: false }),
}))

vi.mock("sonner", () => ({
  toast: { error: toastError, success: toastSuccess },
}))

import { ResolveDialog } from "@/components/issues/resolve-dialog"

beforeAll(() => {
  // jsdom does not implement object URLs used for the preview.
  URL.createObjectURL = vi.fn(() => "blob:preview")
  URL.revokeObjectURL = vi.fn()
})

describe("ResolveDialog", () => {
  beforeEach(() => {
    mutateAsync.mockReset()
    toastError.mockReset()
    toastSuccess.mockReset()
  })

  it("disables submission until a photo is attached", () => {
    render(<ResolveDialog issueId={7} open onOpenChange={() => {}} />)
    expect(screen.getByRole("button", { name: /mark resolved/i })).toBeDisabled()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it("submits the attached photo and notes", async () => {
    mutateAsync.mockResolvedValue({})
    const onOpenChange = vi.fn()
    render(<ResolveDialog issueId={7} open onOpenChange={onOpenChange} />)

    const file = new File(["x"], "after.jpg", { type: "image/jpeg" })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.change(screen.getByLabelText(/notes/i), {
      target: { value: "Pothole filled" },
    })
    fireEvent.click(screen.getByRole("button", { name: /mark resolved/i }))

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        issueId: 7,
        file,
        notes: "Pothole filled",
      })
    )
    expect(toastSuccess).toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
