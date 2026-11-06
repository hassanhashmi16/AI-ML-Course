# WhyTheDiff rename and existing installations

The application, course folder, package metadata, UI, prompts, exports, container
user/service, and GitHub repository now use WhyTheDiff (`whythediff`). The course
project lives at `Phase 1(AI)/PROJECTS/Project-4-WhyTheDiff/`; its standalone repo
is `https://github.com/hassanhashmi16/whythediff`.

Existing local data and reports move with the project folder. Research text and
historical report contents are not rewritten. `retrieval/legacy.py` exposes
pre-rename vector collections through new-name aliases, and manifest loading
reads the previous namespace when necessary. This preserves reusable findings,
embedding compatibility checks, and account isolation without copying vectors.
The previous name appears only in this compatibility code and its fixtures.

The session cookie name has changed. Sign in again if an existing browser
session returns to the landing page; the GitHub account ID still owns the same
saved research. OAuth client credentials, homepage and callback URL do not need
to change merely because of this rename.

For GitHub's displayed consent-page name, edit the existing OAuth application
at **GitHub Settings → Developer settings → OAuth Apps → Application name**
and set **WhyTheDiff**. Update any old name in the app description too. Keep
the existing client ID, secret, homepage and callback unless the host changes.

If migrating an existing Docker deployment, point the renamed Compose service
at the **existing physical state volume** explicitly (the volume's `name` field)
before starting it. A changed Compose project/volume name can otherwise select
an empty volume. Do not delete the old state volume. Stop the old worker before
starting the new one. The container keeps the same numeric UID by default.

The standalone repository history is retained across the course-folder rename.
Future synchronization uses the new prefix and remote:

```powershell
git subtree push --prefix="Phase 1(AI)/PROJECTS/Project-4-WhyTheDiff" whythediff main
```
