import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Bullet, Code } from "../components/primitives";
import { theme } from "../theme";

export const S02_WhatIs: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Fusion nedir?" align="flex-start">
    <div style={{ display: "flex", flexDirection: "column", gap: 28, maxWidth: 1500 }}>
      <Bullet delay={6} color={theme.accent}>
        <b>Terminalde çalışır.</b> Kod tabanını okur, dosya düzenler, komut çalıştırır,
        test eder — tıpkı bir kıdemli geliştirici gibi.
      </Bullet>
      <Bullet delay={20} color={theme.blue}>
        <b>İki motoru vardır:</b> <Code>agent</Code> (araçlarla iş yapar) ve{" "}
        <Code color={theme.blue}>fusion</Code> (birden çok modele sorup en iyisini seçer).
      </Bullet>
      <Bullet delay={34} color={theme.green}>
        <b>Öz-öğrenir.</b> Her görevden ders çıkarır; benzer işlerde bunları hatırlar.
      </Bullet>
      <Bullet delay={48} color={theme.accent2}>
        <b>Ücretsiz çalışır.</b> OpenRouter + NVIDIA NIM ücretsiz katmanı yeter; anahtar
        yoksa bile açılır.
      </Bullet>
    </div>
  </SceneLayout>
);
