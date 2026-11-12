import { test, expect } from '@playwright/test'

test('analyst reviews an alert end to end', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Username').fill('analyst1')
  await page.getByPlaceholder('Password').fill('analyst1-demo')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await page.getByRole('link', { name: 'Alerts', exact: true }).click()
  await page.locator('select').first().selectOption('open')
  await page.locator('tbody a').first().click()

  await page.getByRole('button', { name: 'Create case' }).click()
  await expect(page).toHaveURL(/\/cases\//)

  await page.getByPlaceholder(/Add a factual note/).fill('Reviewed linked transactions; pattern needs review.')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByText('Reviewed linked transactions')).toBeVisible()

  await page.getByPlaceholder(/Rationale/).fill('Customer explained the activity; documents verified.')
  await page.getByRole('button', { name: 'Save disposition' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('closed')
})