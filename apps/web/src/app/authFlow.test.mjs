import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const sourceUrl = new URL("./App.tsx", import.meta.url);

test("daily login uses username and password without bootstrap or browser storage", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(source, /Username/);
  assert.match(source, /type="password"/);
  assert.match(source, /autoComplete="current-password"/);
  assert.match(source, /\/api\/v1\/auth\/login/);
  assert.doesNotMatch(source, /bootstrap\/exchange|localStorage|sessionStorage/);
});

test("login has generic failure, enter submit, loading state, and duplicate-submit guard", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(source, /Credenciais inválidas\./);
  assert.match(source, /<form onSubmit=\{submit\}>/);
  assert.match(source, /if \(busy\) return/);
  assert.match(source, /disabled=\{busy\}/);
  assert.match(source, /setPassword\(""\)/);
});

test("setup and recovery keep bootstrap restricted to explicit flows", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(source, /\/api\/v1\/auth\/setup/);
  assert.match(source, /\/api\/v1\/auth\/recovery/);
  assert.match(source, /password_confirmation/);
  assert.match(source, /Primeiro acesso/);
  assert.match(source, /Recuperação local/);
});

test("persistent session verification skips login and logout uses CSRF", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(source, /\/api\/v1\/auth\/session/);
  assert.match(source, /authenticated\(await api<Session>/);
  assert.match(source, /\/api\/v1\/auth\/logout/);
  assert.match(source, /"X-CSRF-Token": session\.csrf_token/);
  assert.match(source, /"Sair"/);
});

test("authenticated remote screen still receives the session and unauthorized callback", async () => {
  const source = await readFile(sourceUrl, "utf8");

  assert.match(source, /<RemoteScreenPage/);
  assert.match(source, /csrfToken=\{session\.csrf_token\}/);
  assert.match(source, /onUnauthorized=\{showLogin\}/);
});
