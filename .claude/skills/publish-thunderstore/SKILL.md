---
name: publish-thunderstore
description: Check a Thunderstore package ZIP's layout and publish it with Thunderstore's multipart, background-validated upload. Use when releasing a Northstar (or other Thunderstore community) mod or map package, including large packages where the official CLI's synchronous finalize fails.
---

# Publish a package to Thunderstore

`tools/thunderstore_upload.py` uses only the standard library.

Publishing is public and versions are permanent, so get the user's explicit go
ahead before `upload`.

## Procedure

1. **Build the package.** It needs a root `manifest.json`, `README.md` and a
   256x256 `icon.png`.
   - **Layout:** Northstar mods go under `mods/<Author>.<Mod>/`.
   - **Dependencies:** list them in the manifest as `Team-Package-X.Y.Z`. A map
     that needs a shared UI pack depends on it, and the dependency must be
     published first.
2. **Check.** `python tools/thunderstore_upload.py check PACKAGE.zip` must
   list no problems. Also check the version is higher than the published one,
   since Thunderstore never replaces a version.
3. **Upload.**

   ```powershell
   $env:TCLI_AUTH_TOKEN = '<service account token>'   # set by the user; never echo, log or commit it
   python tools/thunderstore_upload.py upload PACKAGE.zip --namespace TEAM --community northstar
   ```

   - **What it does:** uploads in parts, finishes, submits for background
     validation and polls until done. It prints the download URL.
   - **On a timeout:** it prints the submission ID; inspect that before
     retrying.
4. **Confirm.** Check
   `https://thunderstore.io/api/experimental/package/<TEAM>/<NAME>/`: `latest`
   should show the new version with the right dependencies.

## Safety

- **The token:** it is a credential. Read it only from the environment, and
  never put it in arguments, files or logs.
- **CI:** in a CI workflow, pass it as a secret only to the publishing step.
- **Where it goes:** the tool sends it only to the fixed API origin, and keeps
  presigned storage URLs out of errors.
