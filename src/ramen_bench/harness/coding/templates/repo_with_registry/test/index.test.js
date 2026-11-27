"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { loadConfig } = require("../src/index.js");

function write(name, contents) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "confkit-"));
  const file = path.join(dir, name);
  fs.writeFileSync(file, contents);
  return file;
}

test("later files override earlier ones", () => {
  const a = write("a.json", JSON.stringify({ server: { port: 80, host: "localhost" } }));
  const b = write("b.json", JSON.stringify({ server: { port: 8080 } }));
  assert.deepStrictEqual(loadConfig([a, b]), { server: { port: 8080, host: "localhost" } });
});

test("missing files are skipped", () => {
  assert.deepStrictEqual(loadConfig(["/does/not/exist.json"]), {});
});

test("environment overrides nest on double underscores", () => {
  const config = loadConfig([], { env: { APP_SERVER__PORT: "9000", OTHER: "x" }, prefix: "APP_" });
  assert.deepStrictEqual(config, { server: { port: "9000" } });
});
