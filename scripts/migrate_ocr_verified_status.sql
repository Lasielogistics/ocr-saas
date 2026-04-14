-- Migrate to ocr/verified status workflow
-- 1. Add new statuses to check constraint
-- 2. Rename completed -> ocr (OCR done, not verified)
-- 3. Drop manually_reviewed column

ALTER TABLE ocr_documents DROP COLUMN IF EXISTS manually_reviewed;

-- Update existing completed docs to ocr (not yet verified)
UPDATE ocr_documents SET status = 'ocr' WHERE status = 'completed';

-- Update check constraint to use ocr instead of completed, and add verified
ALTER TABLE ocr_documents DROP CONSTRAINT IF EXISTS ocr_documents_status_check;
ALTER TABLE ocr_documents ADD CONSTRAINT ocr_documents_status_check
    CHECK (status IN ('pending', 'queued', 'processing', 'ocr', 'verified', 'failed', 'review'));
