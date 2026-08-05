-- 009: A checklist answer can be resolved by doing the work.
--
-- Completing a plan item has always resolved the *finding* behind it, so the next assessment
-- reflected the work. But the Quick Check produces hazards from checklist answers, not findings,
-- and those had no way to be marked "fixed" — the score sat still no matter what the user did.
-- Nullable timestamp rather than a boolean: knowing *when* something was resolved is what lets a
-- future re-scan honestly ask "is this still true?".

ALTER TABLE checklist_answers ADD COLUMN resolved_at timestamptz;
