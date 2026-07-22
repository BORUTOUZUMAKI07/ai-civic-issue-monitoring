import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

describe("UI Components", () => {
  describe("Button", () => {
    it("renders with default variant", () => {
      render(<Button>Click me</Button>)
      expect(screen.getByText("Click me")).toBeInTheDocument()
    })

    it("renders with destructive variant", () => {
      render(<Button variant="destructive">Delete</Button>)
      expect(screen.getByText("Delete")).toBeInTheDocument()
    })

    it("renders as disabled", () => {
      render(<Button disabled>Disabled</Button>)
      expect(screen.getByText("Disabled")).toBeDisabled()
    })
  })

  describe("Card", () => {
    it("renders card with title", () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Test Card</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Card content</p>
          </CardContent>
        </Card>
      )
      expect(screen.getByText("Test Card")).toBeInTheDocument()
      expect(screen.getByText("Card content")).toBeInTheDocument()
    })
  })

  describe("Badge", () => {
    it("renders badge", () => {
      render(<Badge>New</Badge>)
      expect(screen.getByText("New")).toBeInTheDocument()
    })

    it("renders with variant", () => {
      render(<Badge variant="destructive">Error</Badge>)
      expect(screen.getByText("Error")).toBeInTheDocument()
    })
  })
})
