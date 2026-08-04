-- 006: The scan pipeline — checklist answers, inference jobs, and plan bookkeeping.
--
-- A scan collects two kinds of evidence: photographs the model looks at, and questions the user
-- answers. Both feed the same rules engine, which is why a scan can produce a complete plan even
-- when the model finds nothing — the checklist is not a fallback, it is half the input.

CREATE TABLE checklist_answers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id     uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    -- Matches a question id in app/rules/checklist.py, which in turn matches a rulebook trigger.
    question_id text NOT NULL,
    -- True means "the hazard is present", regardless of how the question is phrased on screen.
    hazard_present boolean NOT NULL,
    answered_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT checklist_answers_one_per_question UNIQUE (scan_id, question_id)
);

CREATE INDEX checklist_answers_scan_idx ON checklist_answers (scan_id);

CREATE TYPE inference_status AS ENUM ('queued', 'running', 'succeeded', 'failed');

-- Uploads enqueue work rather than waiting for it: a homeowner photographing their yard should
-- never watch a spinner while a model runs.
CREATE TABLE inference_jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    photo_id    uuid NOT NULL REFERENCES photos (id) ON DELETE CASCADE,
    status      inference_status NOT NULL DEFAULT 'queued',
    attempts    integer NOT NULL DEFAULT 0,
    -- Which model produced the findings, so a scan's results stay explainable after we retrain.
    model_version text,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz,

    CONSTRAINT inference_jobs_one_per_photo UNIQUE (photo_id),
    CONSTRAINT inference_jobs_attempts_non_negative CHECK (attempts >= 0)
);

CREATE INDEX inference_jobs_queue_idx ON inference_jobs (created_at) WHERE status = 'queued';

-- Which model version produced a finding, for the same reason.
ALTER TABLE findings ADD COLUMN model_version text;

-- Assessments are snapshots, and a scan can be assessed more than once as findings are confirmed
-- or resolved. The latest one is what the client shows.
CREATE INDEX assessments_scan_latest_idx ON assessments (scan_id, created_at DESC);

-- Plan items carry the rule's own metadata so a plan stays readable even if a later rulebook drops
-- or renames the rule that produced it.
ALTER TABLE plan_items
    ADD COLUMN zone text,
    ADD COLUMN severity text,
    ADD COLUMN rule_status text,
    ADD COLUMN caveat text,
    ADD COLUMN score_if_done integer;

ALTER TABLE checklist_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE checklist_answers FORCE ROW LEVEL SECURITY;

CREATE POLICY checklist_answers_own ON checklist_answers
    USING (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = checklist_answers.scan_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = checklist_answers.scan_id AND p.user_id = current_user_id()
    ));

GRANT SELECT, INSERT, UPDATE, DELETE ON checklist_answers TO groundwork_app;
-- Inference jobs are queue state, not user data: the worker owns them and handlers only enqueue.
GRANT SELECT, INSERT ON inference_jobs TO groundwork_app;
