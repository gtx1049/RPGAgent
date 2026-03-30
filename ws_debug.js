const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  page.on('console', msg => console.log('Browser console:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('Page error:', err.message));
  
  console.log('Opening page...');
  await page.goto('http://43.134.81.228:8080/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  console.log('Page loaded');
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_01.png' });
  
  // Check WS status
  const wsStatusBefore = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status before:', wsStatusBefore);
  
  // Try using JavaScript to click the game card
  console.log('\\nTrying JavaScript click on game card...');
  await page.evaluate(() => {
    const cards = document.querySelectorAll('.game-card');
    console.log('Found', cards.length, 'game cards');
    if (cards.length > 0) {
      console.log('Clicking card:', cards[0].querySelector('.game-name').textContent);
      cards[0].click();
    }
  });
  
  await page.waitForTimeout(3000);
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_02.png' });
  
  const wsStatusAfterJS = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status after JS click:', wsStatusAfterJS);
  
  // Check game-select visibility
  const gameSelectVisible = await page.$eval('#game-select', el => {
    const style = window.getComputedStyle(el);
    return { display: style.display, opacity: style.opacity, pointerEvents: style.pointerEvents };
  }).catch(() => 'not found');
  console.log('Game select style:', JSON.stringify(gameSelectVisible));
  
  // Try dispatching a click event directly
  console.log('\\nTrying dispatchEvent click...');
  await page.evaluate(() => {
    const cards = document.querySelectorAll('.game-card');
    if (cards.length > 0) {
      const event = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
      cards[0].dispatchEvent(event);
    }
  });
  
  await page.waitForTimeout(3000);
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_03.png' });
  
  const wsStatusAfterDispatch = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status after dispatch:', wsStatusAfterDispatch);
  
  // Check game-select visibility again
  const gameSelectVisible2 = await page.$eval('#game-select', el => {
    const style = window.getComputedStyle(el);
    return { display: style.display, opacity: style.opacity, pointerEvents: style.pointerEvents };
  }).catch(() => 'not found');
  console.log('Game select style after dispatch:', JSON.stringify(gameSelectVisible2));
  
  // Get all network requests to see if anything was fetched
  console.log('\\n--- Checking page structure ---');
  const allDivs = await page.evaluate(() => {
    const divs = [];
    document.querySelectorAll('div').forEach(d => {
      if (d.id) divs.push(d.id);
    });
    return divs;
  });
  console.log('Div IDs:', allDivs.join(', '));
  
  await browser.close();
  console.log('\\nDebug complete');
})();
