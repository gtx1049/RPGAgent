const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  page.on('console', msg => console.log('Browser console:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('Page error:', err.message));
  
  // Handle dialog events (for the player name prompt)
  page.on('dialog', async dialog => {
    console.log('Dialog detected:', dialog.type(), dialog.message());
    if (dialog.type() === 'prompt') {
      await dialog.accept('测试玩家');
    } else {
      await dialog.dismiss();
    }
  });
  
  console.log('Opening page...');
  await page.goto('http://43.134.81.228:8080/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  console.log('Page loaded');
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_01_initial.png' });
  
  // Check all elements with ws in their id
  const wsElementsBefore = await page.evaluate(() => {
    const els = [];
    document.querySelectorAll('[id*="ws"]').forEach(el => els.push({id: el.id, text: el.textContent}));
    return els;
  });
  console.log('WS elements before game start:', JSON.stringify(wsElementsBefore));
  
  // Click the first game card
  console.log('\\nClicking first game card...');
  await page.evaluate(() => {
    const cards = document.querySelectorAll('.game-card');
    if (cards.length > 0) {
      cards[0].click();
    }
  });
  
  await page.waitForTimeout(5000);
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_02_game_started.png' });
  
  // Check all elements with ws in their id
  const wsElementsAfter = await page.evaluate(() => {
    const els = [];
    document.querySelectorAll('[id*="ws"]').forEach(el => els.push({id: el.id, text: el.textContent}));
    return els;
  });
  console.log('WS elements after game start:', JSON.stringify(wsElementsAfter));
  
  // Check state.connected
  const gameState = await page.evaluate(() => {
    return {
      connected: window.state?.connected,
      sessionId: window.state?.sessionId,
      wsExists: !!window.state?.ws
    };
  });
  console.log('Game state:', JSON.stringify(gameState));
  
  // Check narrative
  const narrativeText = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 500)).catch(() => 'not found');
  console.log('\\nNarrative:', narrativeText);
  
  // Check scene title
  const sceneTitle = await page.$eval('#scene-title', el => el.textContent).catch(() => 'not found');
  console.log('Scene title:', sceneTitle);
  
  // Now test WebSocket disconnect
  console.log('\\n========== WebSocket Disconnect Test ==========');
  
  // Check action buttons
  const actionBtns = await page.$$('.action-btn');
  console.log('Action buttons found:', actionBtns.length);
  
  // Record narrative length before offline action
  const narrativeBeforeOffline = await page.$eval('#narrative', el => el.textContent.length).catch(() => 0);
  console.log('Narrative length before offline action:', narrativeBeforeOffline);
  
  // Set offline mode
  console.log('\\nSetting offline mode...');
  await context.setOffline(true);
  await page.waitForTimeout(2000);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_03_offline.png' });
  
  // Check WS elements after offline
  const wsElementsOffline = await page.evaluate(() => {
    const els = [];
    document.querySelectorAll('[id*="ws"]').forEach(el => els.push({id: el.id, text: el.textContent}));
    return els;
  });
  console.log('WS elements after offline:', JSON.stringify(wsElementsOffline));
  
  // Check game state after offline
  const gameStateOffline = await page.evaluate(() => {
    return {
      connected: window.state?.connected,
      wsReadyState: window.state?.ws?.readyState
    };
  });
  console.log('Game state offline:', JSON.stringify(gameStateOffline));
  
  // Try clicking action button while offline
  if (actionBtns.length > 0) {
    const firstBtnText = await actionBtns[0].textContent();
    console.log('\\nClicking action button while offline:', firstBtnText);
    
    await actionBtns[0].click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_04_offline_action.png' });
    
    // Check narrative after offline action
    const narrativeAfterOfflineAction = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 500)).catch(() => 'not found');
    console.log('Narrative after offline action:', narrativeAfterOfflineAction);
    
    // Check if there's an error message in the narrative
    const hasErrorMsg = narrativeAfterOfflineAction.includes('断开') || narrativeAfterOfflineAction.includes('连接中断') || narrativeAfterOfflineAction.includes('错误');
    console.log('Has disconnect error message:', hasErrorMsg);
  }
  
  // Check if the button is still enabled (was it silently swallowed)
  const btnEnabledAfterOffline = actionBtns.length > 0 ? await actionBtns[0].isEnabled() : false;
  console.log('Button still enabled after offline click:', btnEnabledAfterOffline);
  
  // Re-enable online mode
  console.log('\\n========== Reconnection Test ==========');
  console.log('Re-enabling online mode...');
  await context.setOffline(false);
  
  await page.waitForTimeout(5000);
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_05_reconnected.png' });
  
  // Check game state after reconnect
  const gameStateReconnected = await page.evaluate(() => {
    return {
      connected: window.state?.connected,
      wsReadyState: window.state?.ws?.readyState
    };
  });
  console.log('Game state after reconnect:', JSON.stringify(gameStateReconnected));
  
  // Check WS elements after reconnect
  const wsElementsReconnected = await page.evaluate(() => {
    const els = [];
    document.querySelectorAll('[id*="ws"]').forEach(el => els.push({id: el.id, text: el.textContent}));
    return els;
  });
  console.log('WS elements after reconnect:', JSON.stringify(wsElementsReconnected));
  
  // Try clicking action button after reconnect
  if (actionBtns.length > 0) {
    const btnEnabledAfterRecon = await actionBtns[0].isEnabled();
    console.log('Button enabled after reconnect:', btnEnabledAfterRecon);
    
    console.log('Clicking action button after reconnect...');
    await actionBtns[0].click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_06_reconnect_action.png' });
    
    const narrativeAfterReconAction = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 500)).catch(() => 'not found');
    console.log('Narrative after reconnect action:', narrativeAfterReconAction);
  }
  
  await browser.close();
  console.log('\\n========== Test Complete ==========');
})();
