-- 008: Which state's law applies to a property.
--
-- The rulebook now carries a national advisory base plus per-state statutory rules, so evaluation
-- needs to know where a property is. Nullable on purpose: when we cannot determine the state, the
-- national rules still apply and the user still gets a real assessment — an unknown jurisdiction
-- means fewer citations, never a blank screen.

ALTER TABLE properties ADD COLUMN state_code text;

ALTER TABLE properties ADD CONSTRAINT properties_state_code_shape
    CHECK (state_code IS NULL OR state_code ~ '^[A-Z]{2}$');

COMMENT ON COLUMN properties.state_code IS
    'Two-letter state code deciding which statutory rules are in force. NULL means undetermined,
     in which case only the nationally-applicable advisory rules apply.';
