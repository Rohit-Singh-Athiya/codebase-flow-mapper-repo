import { test as base } from '@playwright/test';
import { CheckoutPage } from '../pages/checkout.page';
export const test = base.extend({ checkout: async ({ page }, use) => use(new CheckoutPage(page)) });
