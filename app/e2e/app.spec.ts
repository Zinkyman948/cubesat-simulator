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

test("ITU-R atmosphere: X-band loses more than S-band, and can be switched off", async ({ page }) => {
  await openApp(page);
  // A Boulder pass: both the S-band and X-band links serve it.
  await page.locator("table.data tbody tr", { hasText: "Boulder" }).first().click();
  await page.getByLabel("Second chart").selectOption("atmosphere");
  const chart = page.locator(".chart").nth(1);
  const readout = async () => {
    // Move away first: re-hovering the same spot on a rebuilt chart fires no event.
    await page.mouse.move(0, 0);
    await chart.locator(".u-over").hover({ position: { x: 30, y: 40 } }); // near AOS, low elevation
    const text = (await chart.locator(".u-legend").textContent()) ?? "";
    const value = (link: string) => Number(new RegExp(`${link}\\s*([\\d.]+) dB`).exec(text)?.[1]);
    return { s: value("S-band payload"), x: value("X-band payload") };
  };

  const withAtmosphere = await readout();
  expect(withAtmosphere.x).toBeGreaterThan(withAtmosphere.s);
  expect(withAtmosphere.s).toBeGreaterThan(0);

  await page.getByLabel("Atmosphere", { exact: true }).selectOption("none");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  await page.locator("table.data tbody tr", { hasText: "Boulder" }).first().click();
  const without = await readout();
  expect(without).toEqual({ s: 0, x: 0 });
});

test("orbit lifetime: estimate, headline, charts, and staleness", async ({ page }) => {
  const errors = trackErrors(page);
  await openApp(page);
  await page.getByRole("tab", { name: "Orbit lifetime" }).click();
  await page.getByRole("button", { name: "Estimate lifetime" }).click();
  // The demo 3U at 500 km with the solar-cycle model re-enters around 2031.
  await expect(page.locator(".hero-label")).toHaveText("Estimated re-entry", { timeout: 60_000 });
  await expect(page.locator(".hero-value")).toContainText("2031");
  await expect(page.locator(".lifetime .chart .uplot")).toHaveCount(2);
  await expect(page.locator(".stat-tiles")).toContainText("0.0215 m²/kg");

  // A heavier spacecraft decays more slowly; the old estimate is flagged as stale.
  await field(page, "Mass").locator("input").fill("8");
  await expect(page.getByText("Scenario changed since this estimate.")).toBeVisible();
  await page.getByRole("button", { name: "Re-estimate" }).click();
  await expect(page.getByText("Scenario changed since this estimate.")).toBeHidden({ timeout: 60_000 });
  const heavier = await page.locator(".hero-value").textContent();
  expect(Number(/(\d{4})/.exec(heavier ?? "")?.[1])).toBeGreaterThan(2031);
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

test("a draft of an older example version offers the updated example", async ({ page }) => {
  await openApp(page);
  const current = await yamlText(page);
  // A draft saved by an older app version: no record of which example it came from.
  const stale = current.replace("name: SSO 3U demo", "name: My old SSO edit");
  await page.evaluate((y) => localStorage.setItem("cubesat-sim:draft:sso_3u_demo", y), stale);
  await page.reload();
  await expect(page.locator(".outdated-notice")).toBeVisible();

  // Keeping the edits dismisses the notice for good.
  await page.getByRole("button", { name: "Keep my edits" }).click();
  await expect(page.locator(".outdated-notice")).toBeHidden();
  await expect(page.locator(".edited-row")).toBeVisible();
  await page.reload();
  await expect(page.locator("table.data tbody tr").first()).toBeVisible();
  await expect(page.locator(".outdated-notice")).toBeHidden();
  await expect(page.locator(".topbar .scenario-name")).toHaveText("My old SSO edit");

  // Loading the updated example replaces the draft.
  await page.evaluate(() => localStorage.removeItem("cubesat-sim:draft-base:sso_3u_demo"));
  await page.reload();
  await page.getByRole("button", { name: "Load updated example" }).click();
  await expect(page.locator(".outdated-notice")).toBeHidden();
  await expect(page.locator(".topbar .scenario-name")).toHaveText("SSO 3U demo");
});

test("tiny values keep meaningful axis labels and readouts", async ({ page }) => {
  await openApp(page);
  // UHF/VHF rain loss is around 1e-5 dB: it must not read as 0.
  await page.locator("table.data tbody tr").first().click();
  await page.getByLabel("Second chart").selectOption("rain");
  const chart = page.locator(".chart").nth(1);
  const ticks = await chart.locator(".u-axis").nth(1).locator(".u-label, div").allTextContents();
  // The chart is rebuilt when the metric changes; retry the hover until the
  // new chart picks it up.
  await expect(async () => {
    await page.mouse.move(0, 0);
    await chart.locator(".u-over").hover({ position: { x: 40, y: 30 } });
    await expect(chart.locator(".u-legend")).toContainText(
      /UHF telemetry\s*[1-9][\d.]*e-\d+ dB|UHF telemetry\s*0\.0+[1-9]\d* dB/,
      { timeout: 1000 },
    );
  }).toPass();
  expect(ticks.join(" ")).not.toMatch(/^(\s*0\s*)+$/);
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
