# Bug Log

Kept live during the build, per `WORKFLOW-RULES.md` §7. This feeds Question 12 ("What broke, and how you got out") directly — write entries the day the bug happens, not reconstructed from memory the night before submission.

Format:
```
## [YYYY-MM-DD] [component] Short title
- **Broke**: what actually happened, observed behavior
- **Root cause**: the real reason, not the symptom
- **Fix**: what changed
- **Time lost**: rough hours
```

---

## [YYYY-MM-DD] [architecture] Example entry — replace with real ones
- **Broke**: Docs specified a Node/Prisma stack; hackathon rubric required Python/FastAPI.
- **Root cause**: Documentation drafted before the track/rubric constraints were finalized.
- **Fix**: Full architecture/code-standards rewrite to FastAPI + Pydantic + SQLAlchemy before any code was written, caught during doc review rather than mid-build.
- **Time lost**: ~1 hour of review, saved a likely full backend rewrite later.
