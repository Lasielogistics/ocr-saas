import { test, expect } from '@playwright/test';

test('sidebar shows Calendar not Appointments', async ({ page }) => {
  await page.goto('http://192.168.50.100:3000/sidebar.html');
  const links = await page.locator('nav ul li a').allTextContents();
  console.log('Sidebar links:', links);
  const calendarLink = links.find(l => l.includes('Calendar'));
  expect(calendarLink).toBeTruthy();
  expect(links.find(l => l.includes('Appointments'))).toBeFalsy();
});
