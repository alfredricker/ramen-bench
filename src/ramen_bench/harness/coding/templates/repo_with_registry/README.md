# confkit

Load layered JSON config files with environment overrides.

## Install

```
npm instal confkit
```

## Usage

```js
const { loadConfig } = require("confkit");

const config = loadConfig(["config/default.json", "config/local.json"], {
  env: process.env,
  prefix: "APP_",
});
```

Later files override earlier ones, and `APP_SERVER__PORT=8080` overrides
`server.port`. Missing files are skipped.

From the command line:

```
npx confkit config/default.json config/local.json
```
