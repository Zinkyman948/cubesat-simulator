import { expect, test, type Locator, type Page } from "@playwright/test";

/** Collect console errors and uncaught exceptions (including CSP violations). */
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

/** The form field whose label is exactly `label` (first match). */
function field(page: Page, label: string): Locator {
  return page.locator(".field", { has: page.locator(`label:text-is("${label}")`) }).first();
}

async function yamlText(page: Page): Promise<string> {
  await page.getByRole("tab", { name: "YAML" }).click();
  const text = await page.getByLabel("Scenario YAML").inputValue();
  await page.getByRole("tab", { name: "Form" }).click();
  return text;
}

async function openApp(page: Page) {
  await page.goto("/");
  // Each test starts from the shipped example, not a draft from another test.
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.locator("table.data tbody tr").first()).toBeVisible();
}

test("loads the demo, renders the globe and charts, with no errors", async ({ page }) => {
  const errors = trackErrors(page);
  await openApp(page);

  await expect(page.locator(".engine-status")).toHaveClass(/ok/);
  await expect(page.locator(".cesium-widget canvas")).toBeVisible();
  // 14 + 3 + 3 passes over 24 h for the SSO demo.
  await expect(page.getByText("Passes (20)")).toBeVisible();
  await expect(page.locator(".chart .uplot")).toHaveCount(4);

  // Selecting another pass updates the chart header.
  await page.locator("table.data tbody tr").nth(4).click();
  await expect(page.locator(".charts-header h2")).toHaveText("Boulder - pass 1");
  expect(errors).toEqual([]);
});

test("form edits validate live, update the YAML and run", async ({ page }) => {
  const errors = trackErrors(page);
  await openApp(page);
  const inclination = field(page, "Inclination").locator("input");

  // Out-of-range value: inline error from the engine's validation.
  await inclination.fill("200");
  await expect(field(page, "Inclination").locator(".field-error")).toContainText("180");
  await expect(page.locator(".issue-count")).toBeVisible();

  // Sun-synchronous helper for a 600 km orbit.
  await field(page, "Altitude").locator("input").fill("600");
  const sso = page.locator(".derived button");
  await expect(sso).toContainText("97.79");
  await sso.click();
  await expect(inclination).toHaveValue("97.79");
  await expect(page.locator(".issue-count")).toBeHidden();
  await expect(page.locator(".derived dd").first()).toContainText("96.7");

  // Add a station and rename one; the S-band link's station list follows.
  await page.getByRole("button", { name: "+ Add ground station" }).click();
  const names = page.locator(".item-card-head input");
  await expect(names).toHaveCount(4);
  await names.nth(1).fill("Boulder CO");
  const yaml = await yamlText(page);
  expect(yaml).toContain("name: Station 4");
  expect(yaml).toContain("stations: [Svalbard, Boulder CO]");
  expect(yaml).toContain("# sun-synchronous at 500 km"); // comments survive form edits

  // Switch the UHF link's ground antenna to a dish.
  const uhf = page.locator(".link-card").first();
  await uhf.locator("summary").click();
  await uhf.getByRole("radiogroup", { name: "Ground antenna" }).getByRole("radio", { name: "Parabolic dish" }).click();
  expect(await yamlText(page)).toContain("dish_diameter_m: 1");

  // Run the edited scenario.
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  await expect(page.locator("table.data tbody td:first-child", { hasText: "Boulder CO" }).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("attitude and antenna patterns drive the spacecraft antenna gain", async ({ page }) => {
  const errors = trackErrors(page);
  await openApp(page);

  // Track the ground station instead of pointing at nadir.
  await page.getByLabel("Attitude").selectOption("target");
  await expect(page.getByText("+Z at the highest visible ground station")).toBeVisible();

  // S-band: swap the patch for a 0.3 m dish on the nadir face.
  const sband = page.locator(".link-card").nth(1);
  await sband.locator("summary").click();
  await sband.getByLabel("Spacecraft antenna").selectOption("dish");
  // The first dish field is the spacecraft's (transmitter); the second is the ground station's.
  await sband.getByRole("textbox", { name: "Dish diameter" }).first().fill("0.3");

  const yaml = await yamlText(page);
  expect(yaml).toMatch(/attitude:\n\s+mode: target/);
  expect(yaml).toContain("pattern: dish");
  await expect(page.locator(".issue-count")).toBeHidden();

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();

  // With target pointing the station sits on boresight, so the 0.3 m dish
  // runs at its 14.4 dBi peak, 10 log10(0.55 (pi 0.3 / 0.1335 m)^2).
  await page.getByLabel("Second chart").selectOption("gain");
  await page.locator("table.data tbody tr").first().click();
  const chart = page.locator(".chart").nth(1);
  await chart.locator(".u-over").hover({ position: { x: 150, y: 40 } });
  await expect(chart.locator(".u-legend")).toContainText(/S-band payload\s*14\.4 dBi/);
  expect(errors).toEqual([]);
});

test("drafts survive a reload and can be reverted", async ({ page }) => {
  await openApp(page);
  await field(page, "Inclination").locator("input").fill("98.1");
  await expect(page.locator(".edited-row")).toBeVisible();

  await page.reload();
  await expect(page.locator("table.data tbody tr").first()).toBeVisible();
  await expect(page.locator(".edited-row")).toBeVisible();
  await expect(field(page, "Inclination").locator("input")).toHaveValue("98.1");

  await page.getByRole("button", { name: "Revert to example" }).click();
  await expect(page.locator(".edited-row")).toBeHidden();
  await expect(field(page, "Inclination").locator("input")).toHaveValue("97.4");
});

test("a YAML syntax error blocks the form with an explanation", async ({ page }) => {
  await openApp(page);
  await page.getByRole("tab", { name: "YAML" }).click();
  await page.getByLabel("Scenario YAML").fill("name: [unclosed");
  await page.getByRole("tab", { name: "Form" }).click();
  await expect(page.locator(".form-blocked")).toBeVisible();
});

test("switching to the ISS TLE example runs SGP4", async ({ page }) => {
  await openApp(page);
  await page.getByLabel("Example scenario").selectOption("iss_tle_sgp4");
  await expect(page.locator(".topbar .scenario-name")).toHaveText("ISS TLE (SGP4)");
  await expect(page.getByRole("radio", { name: "TLE" })).toHaveAttribute("aria-checked", "true");
  await expect(page.locator("table.data tbody tr").first()).toContainText("Bluffton");
});
