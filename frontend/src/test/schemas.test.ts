import { describe, it, expect } from "vitest"
import { loginSchema, registerSchema } from "@/lib/schemas"

describe("schemas", () => {
  describe("loginSchema", () => {
    it("validates correct login data", () => {
      const result = loginSchema.safeParse({ email: "test@test.com", password: "123456" })
      expect(result.success).toBe(true)
    })

    it("rejects invalid email", () => {
      const result = loginSchema.safeParse({ email: "invalid", password: "123456" })
      expect(result.success).toBe(false)
    })

    it("rejects short password", () => {
      const result = loginSchema.safeParse({ email: "test@test.com", password: "123" })
      expect(result.success).toBe(false)
    })
  })

  describe("registerSchema", () => {
    it("validates correct register data", () => {
      const result = registerSchema.safeParse({
        email: "test@test.com",
        password: "123456",
        full_name: "Test User",
        role: "field_worker",
      })
      expect(result.success).toBe(true)
    })

    it("rejects missing full_name", () => {
      const result = registerSchema.safeParse({
        email: "test@test.com",
        password: "123456",
        role: "field_worker",
      })
      expect(result.success).toBe(false)
    })

    it("rejects invalid role", () => {
      const result = registerSchema.safeParse({
        email: "test@test.com",
        password: "123456",
        full_name: "Test User",
        role: "superadmin",
      })
      expect(result.success).toBe(false)
    })
  })
})
