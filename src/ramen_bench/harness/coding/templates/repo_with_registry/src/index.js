"use strict";

const fs = require("node:fs");

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function merge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (isObject(value) && isObject(target[key])) {
      merge(target[key], value);
    } else {
      target[key] = value;
    }
  }
  return target;
}

function readFile(path) {
  if (!fs.existsSync(path)) return {};
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function envOverrides(env, prefix) {
  const result = {};
  for (const [name, value] of Object.entries(env)) {
    if (!name.startsWith(prefix)) continue;
    const path = name.slice(prefix.length).toLowerCase().split("__");
    let node = result;
    for (const key of path.slice(0, -1)) {
      node = node[key] = isObject(node[key]) ? node[key] : {};
    }
    node[path[path.length - 1]] = value;
  }
  return result;
}

function loadConfig(paths, { env = {}, prefix = "APP_" } = {}) {
  const config = {};
  for (const path of paths) merge(config, readFile(path));
  return merge(config, envOverrides(env, prefix));
}

module.exports = { loadConfig, merge, envOverrides };
