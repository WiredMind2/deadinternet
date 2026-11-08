# Definition of done

A story is not Done until:

- [ ] Every acceptance criterion in its item file is checked, each against a real run or test.
- [ ] `python -m pytest` passes with the 85% package-coverage gate intact (backend stories).
- [ ] `npm run build` in `web/` succeeds (dashboard stories).
- [ ] The change is merged to `main` and pushed.
- [ ] The item file's Status field is `Done`.

Keep the box state honest: a story whose criteria cannot be verified stays `In progress`.
