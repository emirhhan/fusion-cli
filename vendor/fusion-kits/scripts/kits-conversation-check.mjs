/** Kabul yanıtı gecikmesi için etiketli tarayıcı taşıma fixture'ı. */
export async function checkConversationNavigation(
  page,
  base,
  sameKitThread = false,
) {
  let release;
  let entered;
  let requestId;
  const waiting = new Promise((resolve) => {
    entered = resolve;
  });
  const blocked = new Promise((resolve) => {
    release = resolve;
  });
  const workspaceResponse = await fetch(`${base}/api/workspace`);
  const workspace = await workspaceResponse.json();
  const conversation = {
    id: 'navigation-fixture-thread',
    dotId: workspace.dots[0].id,
    ownerId: workspace.ownerId,
    title: 'Geciken kabul',
    createdAt: Date.now(),
  };
  await page.route('**/api/workspace', (route) =>
    route.fulfill({
      json: {
        ...workspace,
        conversations: [
          ...workspace.conversations,
          {
            ...conversation,
            id: 'existing-fixture-thread',
            title: 'Mevcut sohbet',
          },
        ],
        setup: { ...workspace.setup, missing: [] },
      },
    }),
  );
  await page.route('**/api/conversations', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    requestId = route.request().postDataJSON().requestId;
    entered();
    await blocked;
    await route.fulfill({ json: conversation }).catch(() => {});
  });
  await page.route('**/api/conversations/requests/*', (route) =>
    route.fulfill({
      json: {
        requestId,
        threadId: conversation.id,
        state: 'completed',
        conversation,
      },
    }),
  );
  try {
    await page.goto(base);
    const composer = page.getByRole('textbox', {
      name: 'Sohbet başlat',
      exact: true,
    });
    await composer.waitFor();
    await composer.fill('Gezinmeden sonra otomatik gönderilmemeli');
    await composer.press('Enter');
    await waiting;
    if (sameKitThread) {
      await page.getByRole('button', { name: /Mevcut sohbet/ }).click();
    } else {
      await page.getByRole('button', { name: /Görevler ve etkinlik/ }).click();
      await page
        .getByRole('button', { name: 'Fusion Kits', exact: true })
        .click();
    }
    release();
    await page.waitForTimeout(200);
    if (sameKitThread) {
      if (
        !(
          await page
            .getByRole('button', { name: /Mevcut sohbet/ })
            .getAttribute('class')
        )?.includes('active')
      )
        throw new Error('Geç kabul mevcut sohbet seçimini ezdi.');
    } else {
      await composer.waitFor();
      if (await page.locator('.live-chat').count())
        throw new Error('Eski oluşturma yanıtı gezinmeyi geri aldı.');
    }
    const markers = await page.evaluate(() =>
      Object.keys(globalThis.localStorage).filter((key) =>
        key.startsWith('kits-conversation:'),
      ),
    );
    if (markers.length !== 1)
      throw new Error('Gezinme sonrası toparlanma kabulü korunmadı.');
    if (
      !sameKitThread &&
      (await composer.inputValue()) !==
        'Gezinmeden sonra otomatik gönderilmemeli'
    )
      throw new Error('Gönderilmemiş görev taslağı kayboldu.');
    return sameKitThread
      ? 'labelled-create-late-response-same-kit-thread-selection-kept'
      : 'labelled-create-late-response-navigation-away-and-back-no-auto-task';
  } finally {
    release();
    await page.unroute('**/api/workspace');
    await page.unroute('**/api/conversations');
    await page.unroute('**/api/conversations/requests/*');
    await page.evaluate(() => {
      for (const key of Object.keys(globalThis.localStorage))
        if (key.startsWith('kits-conversation:'))
          globalThis.localStorage.removeItem(key);
    });
    await page.goto(base);
  }
}
