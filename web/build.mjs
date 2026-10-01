// Builds the web form's static assets into ../src/resume_builder/web_static/assets/:
//   app.css          Tailwind CSS (only the classes index.html / app.js use) + @font-face rules
//   fonts/*.woff2    Geist + JetBrains Mono, latin subset
//   js-yaml.min.js   vendored js-yaml (UMD build exposing the `jsyaml` global)
// The output is committed, so neither the app nor the Docker image needs Node.
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "src", "resume_builder", "web_static", "assets");
const nm = (p) => join(here, "node_modules", p);

mkdirSync(join(out, "fonts"), { recursive: true });

execFileSync(
  process.execPath,
  [
    nm("@tailwindcss/cli/dist/index.mjs"),
    "-i",
    join(here, "src", "input.css"),
    "-o",
    join(out, "app.css"),
    "--minify",
  ],
  { stdio: "inherit", cwd: here },
);

copyFileSync(
  nm("@fontsource-variable/geist/files/geist-latin-wght-normal.woff2"),
  join(out, "fonts", "geist-latin-wght-normal.woff2"),
);
copyFileSync(
  nm(
    "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2",
  ),
  join(out, "fonts", "jetbrains-mono-latin-wght-normal.woff2"),
);
copyFileSync(
  nm("js-yaml/dist/browser/js-yaml.umd.min.js"),
  join(out, "js-yaml.min.js"),
);
