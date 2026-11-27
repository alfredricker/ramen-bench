#!/usr/bin/env node
"use strict";

const { loadConfig } = require("../src/index.js");

const paths = process.argv.slice(2);
if (paths.length === 0) {
  console.error("usage: confkit <config.json>...");
  process.exit(2);
}
console.log(JSON.stringify(loadConfig(paths, { env: process.env }), null, 2));
