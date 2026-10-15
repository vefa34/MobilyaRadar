import { expect, test } from "@playwright/test";

test("register → research (demo) → monitor → companies → detail → sources", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/login");
  await page.getByText("New here? Create a workspace").click();
  await page.getByLabel("Organisation").fill("E2E Exporter");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-1");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.goto("/research/new");
  await page.getByLabel("Describe what you are looking for (Turkish or English)").fill("Gürcistan'da yemek masası ve sandalye toptan satan firmalar");
  await page.getByRole("button", { name: "Parse into parameters" }).click();
  await expect(page.locator("label", { hasText: "Georgia" })).toHaveClass(/bg-brand/);
  await page.getByLabel("Companies wanted").fill("20");
  await page.getByLabel("Budget (USD)").fill("1");
  await page.locator("label", { hasText: "Synthetic demo connector" }).locator("input").check();
  await page.getByRole("button", { name: "Start research" }).click();

  await expect(page).toHaveURL(/\/research\/[0-9a-f-]+$/);
  await expect(page.getByText(/completed( partial)?$/).first()).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "Coverage" }).click();
  await expect(page.getByText("All results are SYNTHETIC")).toBeVisible();

  await page.getByRole("link", { name: "Companies" }).first().click();
  await expect(page.getByText("No companies match")).toBeVisible();
  await page.getByText("synthetic", { exact: true }).click();
  await expect(page.getByText("synthetic demo data", { exact: false }).first()).toBeVisible();
  const first = page.locator("tbody tr a").first();
  await expect(first).toContainText("[DEMO]");
  await first.click();
  await expect(page.getByText("Why this score")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Evidence/ })).toBeVisible();

  await page.goto("/sources");
  await expect(page.getByText("Panjiva (S&P Global)")).toBeVisible();
  await expect(page.getByText("Google Places API (New)")).toBeVisible();
});
