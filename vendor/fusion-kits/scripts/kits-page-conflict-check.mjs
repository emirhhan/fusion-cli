/** Gerçek yerel API ile belge çatışması ve yeniden karşılaştırma regresyonu. */
export async function checkPageConflict(
  page,
  base,
  spaceId,
  pageId,
  screenshot,
) {
  const endpoint = `${base}/api/spaces/${spaceId}/pages/${pageId}`;
  const read = async () => {
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error('Çatışma belgesi okunamadı.');
    return response.json();
  };
  const patch = async (title) => {
    const current = await read();
    const response = await fetch(endpoint, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        content: current.content,
        parentId: current.parentId,
        expectedRevision: current.revision,
      }),
    });
    if (!response.ok) throw new Error('Test sunucusu sürümü değiştirilemedi.');
  };
  const title = page.getByRole('textbox', {
    name: 'Sayfa başlığı',
    exact: true,
  });
  await title.fill('Yerel başlık A');
  await patch('Sunucu başlığı');
  await page
    .getByRole('button', { name: 'Karşılaştır ve birleştir', exact: true })
    .waitFor();
  await page
    .getByRole('button', { name: 'Karşılaştır ve birleştir', exact: true })
    .click();
  const comparison = page.getByRole('region', {
    name: 'Sayfa sürümlerini karşılaştır',
  });
  await comparison.waitFor();
  await comparison
    .getByRole('button', { name: 'Yerel sürümü seç', exact: true })
    .click();
  await comparison.getByRole('checkbox').check();
  await title.fill('Yerel başlık B');
  await page
    .getByRole('button', { name: 'Karşılaştır ve birleştir', exact: true })
    .click();
  await page.waitForFunction(
    () =>
      globalThis.document.querySelector(
        '.page-conflict-panel input:not([type="checkbox"])',
      )?.value === 'Yerel başlık B',
    undefined,
    { timeout: 5000 },
  );
  if (await comparison.getByRole('checkbox').isChecked())
    throw new Error('Yeniden karşılaştırmada önceki onay temizlenmedi.');
  if (
    !(await comparison
      .getByRole('button', { name: 'Birleşimi kaydet', exact: true })
      .isDisabled())
  )
    throw new Error('Yeni birleşim eski onayla kaydedilebilir durumda.');
  await screenshot('kits-page-conflict-compare');
  await comparison.getByRole('checkbox').scrollIntoViewIfNeeded();
  await screenshot('kits-page-conflict-merge');
  const viewport = page.viewportSize();
  await page.setViewportSize({ width: 390, height: 844 });
  await comparison.locator('h2').scrollIntoViewIfNeeded();
  await screenshot('kits-page-conflict-compare-mobile');
  await comparison.getByRole('checkbox').scrollIntoViewIfNeeded();
  await screenshot('kits-page-conflict-merge-mobile');
  if (
    await page.evaluate(
      () =>
        globalThis.document.documentElement.scrollWidth >
        globalThis.innerWidth + 1,
    )
  )
    throw new Error('Birlesim panelinde yatay tasma var.');
  await page.setViewportSize(viewport);

  await comparison
    .getByRole('button', { name: 'Yerel sürümü seç', exact: true })
    .click();
  await comparison.getByRole('checkbox').check();
  await comparison
    .getByRole('button', { name: 'Birleşimi kaydet', exact: true })
    .click();
  try {
    await page
      .locator('.document-notice')
      .filter({ hasText: 'Birleşim güncel sürüm kontrolüyle kaydedildi.' })
      .waitFor({ timeout: 5000 });
  } catch {
    await screenshot('kits-page-conflict-save-failure');
    const notices = await page
      .locator('.document-notice, .document-save-notice')
      .allTextContents();
    throw new Error(
      'Birleşim sonucu doğrulanamadı: ' +
        JSON.stringify({ notices, remote: await read() }),
    );
  }
  if ((await read()).title !== 'Yerel başlık B')
    throw new Error('Birleşim yeni yerel taslağı korumadı.');
  await screenshot('kits-page-conflict-saved');
  await page.reload();
  await title.waitFor();
  if ((await title.inputValue()) !== 'Yerel başlık B')
    throw new Error('Birleşim yeniden açılışta kayboldu.');
  return 'real-api-conflict-recompare-fresh-ack-cas-save-and-reload';
}
