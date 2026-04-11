# Trail 2: Annotations: Save, Resolve, Survive

**Time**: ~12 minutes
**Prerequisite**: Trail 0 (steps 7-8)

*This trail is outlined. The full version will trace a concrete scenario: you save a rationale, keep editing, and watch the annotation resolve, reattach, and eventually go stale.*

---

## Planned sections

**Saving an annotation**: `createAnnotationRecord()` builds the record. The target metadata captures everything needed to find this change again later: excerpt, line context, block key.

**Resolution on every diff**: `resolveAnnotations()` runs after each diff recomputation. For each saved annotation, it tries exact ID match first, then heuristic reattachment using bigram similarity scoring.

**The scoring algorithm**: 60% excerpt similarity, 18% line text, 8% each for before/after lines, plus block key bonus and line distance penalty. Thresholds: 0.74 minimum score, 0.12 minimum margin over runner-up.

**Stale as a first-class state**: when resolution fails, the note goes stale. The UI shows it clearly. The user can manually reattach or dismiss. Marginalia never silently moves a note.

**Try it**: save an annotation, then rewrite the entire paragraph it was attached to. Watch it go stale in real time.

**Check your understanding**: why does the scoring weight excerpt similarity at 60%? Why not 100%?

---

## Key code paths

- `src/lib/utils/annotations.js:createAnnotationRecord()` (line 201)
- `src/lib/utils/annotations.js:buildAnnotationTarget()` (line 152)
- `src/lib/utils/annotations.js:resolveAnnotations()` (line 321)
- `src/lib/utils/annotations.js:scoreDescriptorMatch()` (line 293)
- `src/lib/stores/app.js:resolvedAnnotations` derived store
