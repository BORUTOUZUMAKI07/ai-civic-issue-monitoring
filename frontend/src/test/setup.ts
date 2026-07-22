import "@testing-library/jest-dom/vitest"
import { server } from "./mocks/server"
import { beforeAll, afterAll, afterEach } from "vitest"

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
