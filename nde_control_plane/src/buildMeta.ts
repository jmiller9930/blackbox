/** Semver from package.json; build ID is new on each `vite build`. */
export const APP_SEMVER = __NDE_APP_SEMVER__;
export const APP_BUILD_ID = __NDE_APP_BUILD_ID__;

export function studioVersionLabel(): string {
  const short = APP_BUILD_ID.replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
  return `v${APP_SEMVER} · build ${short}`;
}
